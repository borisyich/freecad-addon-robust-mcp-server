"""Minimal fixed Bearer-token authentication for HTTP MCP transport."""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias

ASGIScope: TypeAlias = dict[str, Any]
ASGIMessage: TypeAlias = dict[str, Any]
ASGIReceive: TypeAlias = Callable[[], Awaitable[ASGIMessage]]
ASGISend: TypeAlias = Callable[[ASGIMessage], Awaitable[None]]
ASGIApp: TypeAlias = Callable[[ASGIScope, ASGIReceive, ASGISend], Awaitable[None]]


class StaticBearerAuthMiddleware:
    """Require one exact ``Authorization: Bearer <token>`` header.

    This middleware intentionally implements only a fixed machine-to-machine
    token. It is not an OAuth authorization server. Non-HTTP ASGI scopes, such
    as application lifespan, are passed through unchanged.
    """

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
    """Log MCP JSON-RPC method names without logging credentials or arguments."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("freecad_mcp.protocol")

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
        body = bytearray()

        while True:
            message = await receive()
            buffered_messages.append(message)

            if message.get("type") == "http.request":
                body.extend(message.get("body", b""))

            if (
                message.get("type") != "http.request"
                or not message.get("more_body", False)
            ):
                break

        method = "unknown"
        target = "-"

        try:
            payload = json.loads(body)

            if isinstance(payload, dict):
                method = str(payload.get("method", "unknown"))
                params = payload.get("params") or {}

                if method == "resources/read":
                    target = str(params.get("uri", "-"))
                elif method == "prompts/get":
                    target = str(params.get("name", "-"))
                elif method == "tools/call":
                    target = str(params.get("name", "-"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            method = "invalid-json"

        message_index = 0

        async def replay_receive() -> ASGIMessage:
            nonlocal message_index

            if message_index < len(buffered_messages):
                message = buffered_messages[message_index]
                message_index += 1
                return message

            # Do not synthesize an endless sequence of empty http.request
            # messages. Streamable HTTP/SSE applications may wait for the
            # real http.disconnect event. Hiding it leaves the ASGI request
            # alive after the response has been sent and can break clients
            # that reuse an MCP session for the following tools/call.
            return await receive()

        response_status: int | None = None
        started_at = time.perf_counter()

        self.logger.info(
            "MCP request started: method=%s target=%s",
            method,
            target,
        )

        async def audit_send(message: ASGIMessage) -> None:
            nonlocal response_status

            if message.get("type") == "http.response.start":
                response_status = int(message.get("status", 0))

            await send(message)

        try:
            await self.app(scope, replay_receive, audit_send)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            self.logger.info(
                "MCP request completed: method=%s target=%s status=%s "
                "duration_ms=%.1f",
                method,
                target,
                response_status,
                duration_ms,
            )