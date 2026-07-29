"""Wire-level MCP response auditing and protocol-shape validation.

The audit layer validates the JSON-RPC entity body emitted by the ASGI MCP
application.  It deliberately runs after FastMCP has converted tool return
values into protocol messages, so it observes the same response body that the
HTTP client receives (before TLS/HTTP framing).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

STABLE_PROTOCOL_VERSIONS = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
LATEST_STABLE_PROTOCOL_VERSION = "2025-11-25"
SPECIFICATION_URLS = {
    version: f"https://modelcontextprotocol.io/specification/{version}"
    for version in STABLE_PROTOCOL_VERSIONS
}
_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(slots=True)
class ProtocolValidationReport:
    """Validation result separated into client-request and server-response issues."""

    protocol_version: str
    method: str
    request_id: str | int | None
    specification_url: str | None = None
    request_errors: list[str] = field(default_factory=list)
    response_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    response_message_count: int = 0

    @property
    def request_valid(self) -> bool:
        return not self.request_errors

    @property
    def response_valid(self) -> bool:
        return not self.response_errors

    @property
    def valid(self) -> bool:
        return self.request_valid and self.response_valid

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "request_valid": self.request_valid,
                "response_valid": self.response_valid,
                "valid": self.valid,
            }
        )
        return payload


def header_dict(headers: list[tuple[bytes, bytes]]) -> dict[str, list[str]]:
    """Decode ASGI headers while preserving repeated values."""
    decoded: dict[str, list[str]] = {}
    for raw_name, raw_value in headers:
        name = raw_name.decode("latin-1").lower()
        value = raw_value.decode("latin-1")
        decoded.setdefault(name, []).append(value)
    return decoded


def first_header(headers: dict[str, list[str]], name: str) -> str | None:
    values = headers.get(name.lower())
    return values[0] if values else None


def parse_jsonrpc_messages(body: bytes, content_type: str | None) -> list[Any]:
    """Parse JSON or SSE-framed JSON-RPC messages from an HTTP entity body."""
    if not body:
        return []

    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    text = body.decode("utf-8")

    if media_type == "text/event-stream" or text.startswith(("event:", "data:")):
        messages: list[Any] = []
        data_lines: list[str] = []
        for line in text.splitlines():
            if not line:
                if data_lines:
                    data = "\n".join(data_lines)
                    if data.strip():
                        messages.append(json.loads(data))
                    data_lines = []
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            data = "\n".join(data_lines)
            if data.strip():
                messages.append(json.loads(data))
        return messages

    payload = json.loads(text)
    return payload if isinstance(payload, list) else [payload]


def _version_at_least(version: str, minimum: str) -> bool:
    if version not in STABLE_PROTOCOL_VERSIONS:
        return version >= minimum
    return STABLE_PROTOCOL_VERSIONS.index(version) >= STABLE_PROTOCOL_VERSIONS.index(
        minimum
    )


def _validate_base64(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{path} must be a base64 string")
        return
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        errors.append(f"{path} is not valid base64")


def _validate_content_block(
    block: Any,
    *,
    path: str,
    protocol_version: str,
    errors: list[str],
) -> None:
    if not isinstance(block, dict):
        errors.append(f"{path} must be an object")
        return

    block_type = block.get("type")
    if block_type == "text":
        if not isinstance(block.get("text"), str):
            errors.append(f"{path}.text must be a string")
        return

    if block_type == "image":
        _validate_base64(block.get("data"), f"{path}.data", errors)
        if not isinstance(block.get("mimeType"), str) or not block.get("mimeType"):
            errors.append(f"{path}.mimeType must be a non-empty string")
        return

    if block_type == "audio":
        if not _version_at_least(protocol_version, "2025-03-26"):
            errors.append(
                f"{path}.type='audio' is not defined by MCP {protocol_version}"
            )
        _validate_base64(block.get("data"), f"{path}.data", errors)
        if not isinstance(block.get("mimeType"), str) or not block.get("mimeType"):
            errors.append(f"{path}.mimeType must be a non-empty string")
        return

    if block_type == "resource":
        resource = block.get("resource")
        if not isinstance(resource, dict):
            errors.append(f"{path}.resource must be an object")
            return
        if not isinstance(resource.get("uri"), str) or not resource.get("uri"):
            errors.append(f"{path}.resource.uri must be a non-empty string")
        has_text = isinstance(resource.get("text"), str)
        has_blob = isinstance(resource.get("blob"), str)
        if not has_text and not has_blob:
            errors.append(f"{path}.resource must contain text or blob")
        if has_blob:
            _validate_base64(resource.get("blob"), f"{path}.resource.blob", errors)
        return

    if block_type == "resource_link":
        if not _version_at_least(protocol_version, "2025-06-18"):
            errors.append(
                f"{path}.type='resource_link' is not defined by MCP {protocol_version}"
            )
        if not isinstance(block.get("uri"), str) or not block.get("uri"):
            errors.append(f"{path}.uri must be a non-empty string")
        if not isinstance(block.get("name"), str) or not block.get("name"):
            errors.append(f"{path}.name must be a non-empty string")
        return

    errors.append(f"{path}.type has unsupported value {block_type!r}")


def _validate_output_schema(
    structured: Any,
    output_schema: dict[str, Any],
    errors: list[str],
) -> None:
    try:
        from jsonschema import validators

        validator_cls = validators.validator_for(output_schema)
        validator_cls.check_schema(output_schema)
        validation_errors = sorted(
            validator_cls(output_schema).iter_errors(structured),
            key=lambda item: list(item.absolute_path),
        )
        for error in validation_errors:
            location = ".".join(str(item) for item in error.absolute_path)
            suffix = f" at {location}" if location else ""
            errors.append(f"result.structuredContent{suffix}: {error.message}")
    except ImportError:
        errors.append("jsonschema is unavailable; outputSchema could not be validated")
    except Exception as exc:
        errors.append(f"outputSchema validation failed: {exc}")


def _validate_call_tool_result(
    result: Any,
    *,
    protocol_version: str,
    output_schema: dict[str, Any] | None,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(result, dict):
        errors.append("tools/call result must be an object")
        return

    content = result.get("content")
    if not isinstance(content, list):
        errors.append("tools/call result.content is required and must be an array")
    else:
        for index, block in enumerate(content):
            _validate_content_block(
                block,
                path=f"result.content[{index}]",
                protocol_version=protocol_version,
                errors=errors,
            )

    if "isError" in result and not isinstance(result["isError"], bool):
        errors.append("tools/call result.isError must be a boolean")

    structured = result.get("structuredContent")
    if structured is not None:
        if not isinstance(structured, dict):
            errors.append("tools/call result.structuredContent must be an object")
        if not _version_at_least(protocol_version, "2025-06-18"):
            warnings.append(
                f"structuredContent was introduced in MCP 2025-06-18; "
                f"a {protocol_version} client may ignore it"
            )

    if protocol_version == "2025-11-25":
        try:
            from mcp.types import CallToolResult

            CallToolResult.model_validate(result)
        except Exception as exc:
            errors.append(
                "official mcp.types.CallToolResult validation failed: "
                f"{type(exc).__name__}: {exc}"
            )

    if output_schema is not None:
        if not _version_at_least(protocol_version, "2025-06-18"):
            warnings.append(
                f"outputSchema was introduced in MCP 2025-06-18; "
                f"a {protocol_version} client may ignore it"
            )
        elif structured is None:
            errors.append(
                "tool advertises outputSchema but tools/call returned no structuredContent"
            )
        else:
            _validate_output_schema(structured, output_schema, errors)


def _validate_tools_list(
    result: Any,
    *,
    protocol_version: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
        errors.append("tools/list result.tools is required and must be an array")
        return

    for index, tool in enumerate(result["tools"]):
        path = f"result.tools[{index}]"
        if not isinstance(tool, dict):
            errors.append(f"{path} must be an object")
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{path}.name must be a non-empty string")
        elif _version_at_least(protocol_version, "2025-11-25"):
            if len(name) > 128 or not _TOOL_NAME_PATTERN.fullmatch(name):
                warnings.append(
                    f"{path}.name={name!r} does not follow MCP 2025-11-25 "
                    "tool-name guidance"
                )
        input_schema = tool.get("inputSchema")
        if not isinstance(input_schema, dict):
            errors.append(f"{path}.inputSchema must be an object")
        elif input_schema.get("type") != "object":
            errors.append(f"{path}.inputSchema.type must be 'object'")
        if "outputSchema" in tool:
            if not isinstance(tool["outputSchema"], dict):
                errors.append(f"{path}.outputSchema must be an object")
            if not _version_at_least(protocol_version, "2025-06-18"):
                warnings.append(
                    f"{path}.outputSchema is not defined by MCP {protocol_version}"
                )


def validate_jsonrpc_exchange(
    *,
    request: Any,
    response_messages: list[Any],
    protocol_version: str,
    request_headers: dict[str, list[str]] | None = None,
    tool_definition: dict[str, Any] | None = None,
    http_status: int | None = None,
) -> ProtocolValidationReport:
    """Validate one MCP HTTP exchange against stable protocol revision rules."""
    method = request.get("method", "unknown") if isinstance(request, dict) else "unknown"
    request_id = request.get("id") if isinstance(request, dict) else None
    report = ProtocolValidationReport(
        protocol_version=protocol_version,
        method=str(method),
        request_id=request_id,
        specification_url=SPECIFICATION_URLS.get(protocol_version),
        response_message_count=len(response_messages),
    )

    if protocol_version not in STABLE_PROTOCOL_VERSIONS:
        report.warnings.append(
            f"No exact stable validation profile for {protocol_version}; "
            f"using {LATEST_STABLE_PROTOCOL_VERSION} field rules"
        )

    if not isinstance(request, dict):
        report.request_errors.append("request must be a JSON object")
        return report
    if request.get("jsonrpc") != "2.0":
        report.request_errors.append("request.jsonrpc must equal '2.0'")
    if not isinstance(method, str):
        report.request_errors.append("request.method must be a string")

    headers = request_headers or {}
    if method != "initialize" and _version_at_least(protocol_version, "2025-06-18"):
        header_version = first_header(headers, "mcp-protocol-version")
        if header_version is None:
            report.request_errors.append(
                "MCP-Protocol-Version header is required on HTTP requests after initialize"
            )
        elif header_version != protocol_version:
            report.request_errors.append(
                "MCP-Protocol-Version header does not match the negotiated version: "
                f"{header_version!r} != {protocol_version!r}"
            )

    is_notification = request_id is None
    if is_notification:
        if response_messages:
            report.response_errors.append("notifications must not receive JSON-RPC responses")
        if http_status not in (None, 202, 204):
            report.response_errors.append(
                f"notification HTTP response should be 202/204, got {http_status}"
            )
        return report

    if len(response_messages) != 1:
        report.response_errors.append(
            f"request must receive exactly one JSON-RPC response, got {len(response_messages)}"
        )
        return report

    response = response_messages[0]
    if not isinstance(response, dict):
        report.response_errors.append("response must be a JSON object")
        return report
    if response.get("jsonrpc") != "2.0":
        report.response_errors.append("response.jsonrpc must equal '2.0'")
    if response.get("id") != request_id:
        report.response_errors.append(
            f"response.id must match request.id: {response.get('id')!r} != {request_id!r}"
        )

    has_result = "result" in response
    has_error = "error" in response
    if has_result == has_error:
        report.response_errors.append(
            "response must contain exactly one of 'result' or 'error'"
        )
        return report

    if has_error:
        error = response["error"]
        if not isinstance(error, dict):
            report.response_errors.append("response.error must be an object")
        else:
            if not isinstance(error.get("code"), int):
                report.response_errors.append("response.error.code must be an integer")
            if not isinstance(error.get("message"), str):
                report.response_errors.append("response.error.message must be a string")
        return report

    result = response["result"]
    if method == "initialize":
        if not isinstance(result, dict):
            report.response_errors.append("initialize result must be an object")
        else:
            if not isinstance(result.get("protocolVersion"), str):
                report.response_errors.append(
                    "initialize result.protocolVersion must be a string"
                )
            if not isinstance(result.get("capabilities"), dict):
                report.response_errors.append(
                    "initialize result.capabilities must be an object"
                )
            server_info = result.get("serverInfo")
            if not isinstance(server_info, dict):
                report.response_errors.append(
                    "initialize result.serverInfo must be an object"
                )
            elif not isinstance(server_info.get("name"), str) or not isinstance(
                server_info.get("version"), str
            ):
                report.response_errors.append(
                    "initialize result.serverInfo requires string name and version"
                )
        return report

    if method == "tools/list":
        _validate_tools_list(
            result,
            protocol_version=protocol_version,
            errors=report.response_errors,
            warnings=report.warnings,
        )
        return report

    if method == "tools/call":
        output_schema = None
        if isinstance(tool_definition, dict):
            candidate = tool_definition.get("outputSchema")
            if isinstance(candidate, dict):
                output_schema = candidate
        _validate_call_tool_result(
            result,
            protocol_version=protocol_version,
            output_schema=output_schema,
            errors=report.response_errors,
            warnings=report.warnings,
        )
        return report

    if not isinstance(result, dict):
        report.response_errors.append(f"{method} result must be an object")
    return report


def _binary_marker(value: str, *, label: str) -> str:
    digest = hashlib.sha256(value.encode("ascii", errors="ignore")).hexdigest()
    return (
        f"<{label} omitted; base64_chars={len(value)}; "
        f"approx_binary_bytes={(len(value) * 3) // 4}; sha256={digest}>"
    )


def sanitize_wire_payload(value: Any, *, key: str | None = None) -> Any:
    """Redact credentials and binary base64 while preserving protocol structure."""
    if isinstance(value, dict):
        block_type = value.get("type")
        sanitized: dict[str, Any] = {}
        for item_key, item_value in value.items():
            lowered = str(item_key).lower()
            if any(
                token in lowered
                for token in ("authorization", "access_token", "password", "secret")
            ):
                sanitized[str(item_key)] = "<redacted>"
            elif item_key == "data" and block_type in {"image", "audio"} and isinstance(
                item_value, str
            ):
                sanitized[str(item_key)] = _binary_marker(
                    item_value, label=f"{block_type} data"
                )
            elif item_key == "blob" and isinstance(item_value, str):
                sanitized[str(item_key)] = _binary_marker(
                    item_value, label="resource blob"
                )
            else:
                sanitized[str(item_key)] = sanitize_wire_payload(
                    item_value, key=str(item_key)
                )
        return sanitized
    if isinstance(value, list):
        return [sanitize_wire_payload(item, key=key) for item in value]
    return value


def sanitized_wire_text(messages: list[Any], *, max_chars: int) -> str:
    """Render a console-safe representation of the final wire response."""
    safe = sanitize_wire_payload(messages[0] if len(messages) == 1 else messages)
    rendered = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) <= max_chars:
        return rendered
    return rendered[:max_chars] + f"<truncated; total_chars={len(rendered)}>"
