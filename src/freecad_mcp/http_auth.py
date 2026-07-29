"""Bearer authentication plus MCP HTTP method and wire-response auditing."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

from freecad_mcp.protocol_audit import (
    first_header,
    header_dict,
    parse_jsonrpc_messages,
    sanitized_wire_text,
    validate_jsonrpc_exchange,
)

ASGIScope: TypeAlias = dict[str, Any]
ASGIMessage: TypeAlias = dict[str, Any]
ASGIReceive: TypeAlias = Callable[[], Awaitable[ASGIMessage]]
ASGISend: TypeAlias = Callable[[ASGIMessage], Awaitable[None]]
ASGIApp: TypeAlias = Callable[[ASGIScope, ASGIReceive, ASGISend], Awaitable[None]]


class StaticBearerAuthMiddleware:
    """Require one exact ``Authorization: Bearer <token>`` header."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        if len(token) < 32:
            raise ValueError("Bearer token must contain at least 32 characters")
        self.app = app
        self._expected_header = f"Bearer {token}".encode("utf-8")

    async def __call__(
        self,
        scope: ASGIScope,
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        authorization_values = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"authorization"
        ]

        authorized = (
            len(authorization_values) == 1
            and secrets.compare_digest(
                authorization_values[0],
                self._expected_header,
            )
        )
        if authorized:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {
                "error": "unauthorized",
                "error_description": "A valid Bearer token is required",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"www-authenticate", b"Bearer"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class McpMethodAuditMiddleware:
    """Audit parsed MCP methods and the final HTTP entity body sent to clients.

    The internal tool-result log in ``FreecadFastMCP.call_tool`` runs before the
    low-level MCP server wraps the value in JSON-RPC.  This middleware runs at
    the outer ASGI boundary and therefore records the final response body and
    response headers emitted to the SaaS connector.

    When raw saving is enabled, the unmodified body is stored on disk.  Console
    output preserves the complete JSON structure but replaces image/audio/blob
    base64 with a length and SHA-256 marker.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        wire_audit_enabled: bool = False,
        wire_audit_dir: str | Path = "logs/mcp-wire",
        wire_save_raw: bool = False,
        wire_console_body: bool = False,
        wire_console_max_chars: int = 20_000,
        wire_capture_max_bytes: int = 128 * 1024 * 1024,
        wire_validate: bool = True,
    ) -> None:
        self.app = app
        self.logger = logging.getLogger("freecad_mcp.protocol")
        self.wire_audit_enabled = wire_audit_enabled
        self.wire_audit_dir = Path(wire_audit_dir).expanduser().resolve()
        self.wire_save_raw = wire_save_raw
        self.wire_console_body = wire_console_body
        self.wire_console_max_chars = wire_console_max_chars
        self.wire_capture_max_bytes = wire_capture_max_bytes
        self.wire_validate = wire_validate
        self._session_protocols: dict[str, str] = {}
        self._session_tools: dict[str, dict[str, dict[str, Any]]] = {}

    async def __call__(
        self,
        scope: ASGIScope,
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        buffered_messages: list[ASGIMessage] = []
        request_body = bytearray()

        while True:
            message = await receive()
            buffered_messages.append(message)

            if message.get("type") == "http.request":
                request_body.extend(message.get("body", b""))

            if (
                message.get("type") != "http.request"
                or not message.get("more_body", False)
            ):
                break

        payload: Any = None
        method = "unknown"
        target = "-"
        request_id: str | int | None = None
        try:
            payload = json.loads(request_body)
            if isinstance(payload, dict):
                method = str(payload.get("method", "unknown"))
                request_id = payload.get("id")
                params = payload.get("params") or {}
                if method == "resources/read":
                    target = str(params.get("uri", "-"))
                elif method == "prompts/get":
                    target = str(params.get("name", "-"))
                elif method == "tools/call":
                    target = str(params.get("name", "-"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            method = "invalid-json"

        request_headers_raw = list(scope.get("headers", []))
        request_headers = header_dict(request_headers_raw)
        incoming_session_id = first_header(request_headers, "mcp-session-id")
        header_protocol_version = first_header(
            request_headers, "mcp-protocol-version"
        )
        requested_protocol_version: str | None = None
        if method == "initialize" and isinstance(payload, dict):
            params = payload.get("params")
            if isinstance(params, dict) and isinstance(
                params.get("protocolVersion"), str
            ):
                requested_protocol_version = params["protocolVersion"]

        protocol_version = (
            requested_protocol_version
            or header_protocol_version
            or (
                self._session_protocols.get(incoming_session_id)
                if incoming_session_id
                else None
            )
            or "2025-03-26"
        )

        message_index = 0

        async def replay_receive() -> ASGIMessage:
            nonlocal message_index
            if message_index < len(buffered_messages):
                replayed = buffered_messages[message_index]
                message_index += 1
                return replayed
            return await receive()

        response_status: int | None = None
        response_headers_raw: list[tuple[bytes, bytes]] = []
        response_body = bytearray()
        response_body_bytes = 0
        response_hasher = hashlib.sha256()
        capture_truncated = False
        started_at = time.perf_counter()

        self.logger.info(
            "MCP request started: method=%s target=%s request_id=%r "
            "protocol=%s session_id=%s",
            method,
            target,
            request_id,
            protocol_version,
            incoming_session_id or "-",
        )

        async def audit_send(message: ASGIMessage) -> None:
            nonlocal response_status, response_headers_raw
            nonlocal response_body_bytes, capture_truncated

            if message.get("type") == "http.response.start":
                response_status = int(message.get("status", 0))
                response_headers_raw = list(message.get("headers", []))
            elif message.get("type") == "http.response.body":
                chunk = message.get("body", b"") or b""
                response_body_bytes += len(chunk)
                response_hasher.update(chunk)
                remaining = self.wire_capture_max_bytes - len(response_body)
                if remaining > 0:
                    response_body.extend(chunk[:remaining])
                if len(chunk) > max(remaining, 0):
                    capture_truncated = True

            await send(message)

        try:
            await self.app(scope, replay_receive, audit_send)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            response_headers = header_dict(response_headers_raw)
            content_type = first_header(response_headers, "content-type")
            response_session_id = first_header(response_headers, "mcp-session-id")
            session_id = response_session_id or incoming_session_id
            response_sha256 = response_hasher.hexdigest()

            messages: list[Any] = []
            parse_error: str | None = None
            if not capture_truncated:
                try:
                    messages = parse_jsonrpc_messages(bytes(response_body), content_type)
                except Exception as exc:
                    parse_error = f"{type(exc).__name__}: {exc}"

            negotiated_protocol = protocol_version
            if method == "initialize" and messages:
                first_message = messages[0]
                if isinstance(first_message, dict):
                    result = first_message.get("result")
                    if isinstance(result, dict) and isinstance(
                        result.get("protocolVersion"), str
                    ):
                        negotiated_protocol = result["protocolVersion"]
                        if session_id:
                            self._session_protocols[session_id] = negotiated_protocol

            if method == "tools/list" and session_id and messages:
                first_message = messages[0]
                if isinstance(first_message, dict):
                    result = first_message.get("result")
                    tools = result.get("tools") if isinstance(result, dict) else None
                    if isinstance(tools, list):
                        self._session_tools[session_id] = {
                            str(tool.get("name")): tool
                            for tool in tools
                            if isinstance(tool, dict) and tool.get("name")
                        }

            tool_definition = None
            if method == "tools/call" and session_id:
                tool_definition = self._session_tools.get(session_id, {}).get(target)

            report = None
            if self.wire_validate and parse_error is None and not capture_truncated:
                report = validate_jsonrpc_exchange(
                    request=payload,
                    response_messages=messages,
                    protocol_version=negotiated_protocol,
                    request_headers=request_headers,
                    tool_definition=tool_definition,
                    http_status=response_status,
                )

            audit_paths: dict[str, str] = {}
            if self.wire_audit_enabled:
                audit_paths = self._write_wire_audit(
                    method=method,
                    target=target,
                    request_id=request_id,
                    protocol_version=negotiated_protocol,
                    session_id=session_id,
                    request_headers=request_headers,
                    request_body=bytes(request_body),
                    response_status=response_status,
                    response_headers=response_headers,
                    response_body=bytes(response_body),
                    response_body_bytes=response_body_bytes,
                    response_sha256=response_sha256,
                    content_type=content_type,
                    capture_truncated=capture_truncated,
                    parse_error=parse_error,
                    report=report.to_dict() if report else None,
                )

            self.logger.info(
                "MCP wire response: method=%s target=%s request_id=%r "
                "protocol=%s status=%s content_type=%s bytes=%d sha256=%s "
                "session_id=%s capture_complete=%s raw_body=%s metadata=%s",
                method,
                target,
                request_id,
                negotiated_protocol,
                response_status,
                content_type or "-",
                response_body_bytes,
                response_sha256,
                session_id or "-",
                not capture_truncated,
                audit_paths.get("response_body", "disabled"),
                audit_paths.get("metadata", "disabled"),
            )

            if self.wire_console_body and messages and parse_error is None:
                self.logger.info(
                    "MCP wire body sent to client (binary redacted only): %s",
                    sanitized_wire_text(
                        messages,
                        max_chars=self.wire_console_max_chars,
                    ),
                )
            elif parse_error:
                self.logger.error("MCP wire body parse failed: %s", parse_error)
            elif capture_truncated:
                self.logger.error(
                    "MCP wire capture exceeded %d bytes; SHA-256 covers the full "
                    "body but the in-memory validation copy is incomplete",
                    self.wire_capture_max_bytes,
                )

            if report is not None:
                log_method = self.logger.info if report.response_valid else self.logger.error
                log_method(
                    "MCP specification validation: method=%s target=%s "
                    "protocol=%s request=%s response=%s request_errors=%s "
                    "response_errors=%s warnings=%s",
                    method,
                    target,
                    negotiated_protocol,
                    "PASS" if report.request_valid else "FAIL",
                    "PASS" if report.response_valid else "FAIL",
                    json.dumps(report.request_errors, ensure_ascii=False),
                    json.dumps(report.response_errors, ensure_ascii=False),
                    json.dumps(report.warnings, ensure_ascii=False),
                )

            self.logger.info(
                "MCP request completed: method=%s target=%s status=%s "
                "duration_ms=%.1f",
                method,
                target,
                response_status,
                duration_ms,
            )

    def _write_wire_audit(
        self,
        *,
        method: str,
        target: str,
        request_id: str | int | None,
        protocol_version: str,
        session_id: str | None,
        request_headers: dict[str, list[str]],
        request_body: bytes,
        response_status: int | None,
        response_headers: dict[str, list[str]],
        response_body: bytes,
        response_body_bytes: int,
        response_sha256: str,
        content_type: str | None,
        capture_truncated: bool,
        parse_error: str | None,
        report: dict[str, Any] | None,
    ) -> dict[str, str]:
        self.wire_audit_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        safe_method = re.sub(r"[^A-Za-z0-9_.-]+", "_", method)
        safe_target = re.sub(r"[^A-Za-z0-9_.-]+", "_", target)[:80]
        prefix = f"{timestamp}_{uuid.uuid4().hex[:10]}_{safe_method}_{safe_target}"

        metadata_path = self.wire_audit_dir / f"{prefix}.meta.json"
        request_path = self.wire_audit_dir / f"{prefix}.request.json"
        media_type = (content_type or "").split(";", 1)[0].lower()
        response_suffix = (
            ".response.sse" if media_type == "text/event-stream" else ".response.json"
        )
        if capture_truncated:
            response_suffix = ".partial" + response_suffix
        response_path = self.wire_audit_dir / f"{prefix}{response_suffix}"

        request_path.write_bytes(request_body)
        if self.wire_save_raw:
            response_path.write_bytes(response_body)

        safe_request_headers = {
            name: values
            for name, values in request_headers.items()
            if name not in {"authorization", "cookie"}
        }
        metadata = {
            "audit_format": "freecad-mcp-wire-audit-v1",
            "captured_at_utc": timestamp,
            "method": method,
            "target": target,
            "request_id": request_id,
            "protocol_version": protocol_version,
            "session_id": session_id,
            "request_headers": safe_request_headers,
            "request_body_path": str(request_path),
            "request_body_bytes": len(request_body),
            "request_body_sha256": hashlib.sha256(request_body).hexdigest(),
            "response_status": response_status,
            "response_headers": response_headers,
            "response_body_path": str(response_path) if self.wire_save_raw else None,
            "exact_response_body_saved": self.wire_save_raw and not capture_truncated,
            "response_body_bytes": response_body_bytes,
            "response_body_sha256": response_sha256,
            "capture_complete": not capture_truncated,
            "parse_error": parse_error,
            "validation": report,
            "notes": (
                "The response body file contains the exact ASGI HTTP entity body "
                "emitted to the client. TLS and HTTP framing are outside ASGI and "
                "are not part of the JSON-RPC payload. Response headers are the "
                "application-emitted headers; Uvicorn or a proxy may add Date, "
                "Server, Transfer-Encoding, or other transport headers."
            ),
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "request_body": str(request_path),
            "response_body": str(response_path) if self.wire_save_raw else "disabled",
            "metadata": str(metadata_path),
        }
