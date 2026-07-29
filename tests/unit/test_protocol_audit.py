"""Protocol-revision and final-wire validation tests."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import pytest

from freecad_mcp.http_auth import McpMethodAuditMiddleware
from freecad_mcp.protocol_audit import (
    STABLE_PROTOCOL_VERSIONS,
    parse_jsonrpc_messages,
    sanitize_wire_payload,
    validate_jsonrpc_exchange,
)


def _request(method: str, request_id: int | None = 1, params=None):
    payload = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    return payload


def _response(result, request_id: int = 1):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _headers(version: str):
    return {"mcp-protocol-version": [version]}


@pytest.mark.parametrize("version", STABLE_PROTOCOL_VERSIONS)
def test_text_call_tool_result_valid_for_all_stable_revisions(version):
    request = _request("tools/call", params={"name": "list_documents", "arguments": {}})
    response = _response(
        {
            "content": [
                {
                    "type": "text",
                    "text": '[{"name":"Unnamed","object_count":0}]',
                }
            ],
            "isError": False,
        }
    )
    report = validate_jsonrpc_exchange(
        request=request,
        response_messages=[response],
        protocol_version=version,
        request_headers={} if version < "2025-06-18" else _headers(version),
        http_status=200,
    )
    assert report.request_valid, report.request_errors
    assert report.response_valid, report.response_errors


@pytest.mark.parametrize("version", STABLE_PROTOCOL_VERSIONS)
def test_text_plus_image_call_tool_result_valid_for_all_stable_revisions(version):
    image_data = base64.b64encode(b"valid png placeholder").decode("ascii")
    request = _request("tools/call", params={"name": "open_image", "arguments": {}})
    response = _response(
        {
            "content": [
                {"type": "text", "text": '{"success":true}'},
                {"type": "image", "data": image_data, "mimeType": "image/png"},
            ],
            "structuredContent": {"success": True},
            "isError": False,
        }
    )
    report = validate_jsonrpc_exchange(
        request=request,
        response_messages=[response],
        protocol_version=version,
        request_headers={} if version < "2025-06-18" else _headers(version),
        http_status=200,
    )
    assert report.response_valid, report.response_errors
    if version < "2025-06-18":
        assert any("structuredContent" in warning for warning in report.warnings)


@pytest.mark.parametrize("version", STABLE_PROTOCOL_VERSIONS)
def test_missing_content_fails_every_stable_revision(version):
    request = _request("tools/call", params={"name": "broken", "arguments": {}})
    response = _response({})
    report = validate_jsonrpc_exchange(
        request=request,
        response_messages=[response],
        protocol_version=version,
        request_headers={} if version < "2025-06-18" else _headers(version),
        http_status=200,
    )
    assert not report.response_valid
    assert "result.content is required" in " ".join(report.response_errors)


def test_audio_added_after_2024_revision():
    audio = base64.b64encode(b"audio").decode("ascii")
    request = _request("tools/call", params={"name": "audio", "arguments": {}})
    response = _response(
        {"content": [{"type": "audio", "data": audio, "mimeType": "audio/wav"}]}
    )

    old = validate_jsonrpc_exchange(
        request=request,
        response_messages=[response],
        protocol_version="2024-11-05",
        request_headers={},
        http_status=200,
    )
    new = validate_jsonrpc_exchange(
        request=request,
        response_messages=[response],
        protocol_version="2025-03-26",
        request_headers={},
        http_status=200,
    )
    assert not old.response_valid
    assert new.response_valid


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
def test_output_schema_requires_matching_structured_content(version):
    request = _request("tools/call", params={"name": "structured", "arguments": {}})
    tool = {
        "name": "structured",
        "inputSchema": {"type": "object"},
        "outputSchema": {
            "type": "object",
            "properties": {"success": {"type": "boolean"}},
            "required": ["success"],
        },
    }
    valid = _response(
        {
            "content": [{"type": "text", "text": '{"success":true}'}],
            "structuredContent": {"success": True},
        }
    )
    invalid = _response(
        {
            "content": [{"type": "text", "text": "missing structured output"}],
        }
    )

    valid_report = validate_jsonrpc_exchange(
        request=request,
        response_messages=[valid],
        protocol_version=version,
        request_headers=_headers(version),
        tool_definition=tool,
        http_status=200,
    )
    invalid_report = validate_jsonrpc_exchange(
        request=request,
        response_messages=[invalid],
        protocol_version=version,
        request_headers=_headers(version),
        tool_definition=tool,
        http_status=200,
    )
    assert valid_report.response_valid, valid_report.response_errors
    assert not invalid_report.response_valid


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
def test_protocol_version_header_required_after_initialize(version):
    request = _request("tools/list", params={})
    response = _response({"tools": []})
    report = validate_jsonrpc_exchange(
        request=request,
        response_messages=[response],
        protocol_version=version,
        request_headers={},
        http_status=200,
    )
    assert not report.request_valid
    assert "MCP-Protocol-Version" in " ".join(report.request_errors)
    assert report.response_valid


def test_current_sdk_call_tool_result_model_accepts_text_and_image():
    from mcp.types import CallToolResult

    image_data = base64.b64encode(b"image").decode("ascii")
    payload = {
        "content": [
            {"type": "text", "text": '{"success":true}'},
            {"type": "image", "data": image_data, "mimeType": "image/png"},
        ],
        "structuredContent": {"success": True},
        "isError": False,
    }
    parsed = CallToolResult.model_validate(payload)
    assert len(parsed.content) == 2
    assert parsed.isError is False


def test_binary_sanitizer_preserves_shape_and_hashes_payload():
    data = base64.b64encode(b"secret image bytes").decode("ascii")
    safe = sanitize_wire_payload(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {"type": "image", "data": data, "mimeType": "image/png"}
                ]
            },
        }
    )
    marker = safe["result"]["content"][0]["data"]
    assert data not in marker
    assert "base64_chars=" in marker
    assert "sha256=" in marker


@pytest.mark.asyncio
async def test_wire_audit_saves_exact_final_body_and_validates(tmp_path, caplog):
    image_data = base64.b64encode(b"wire image").decode("ascii")
    request_payload = _request(
        "tools/call",
        params={"name": "open_image", "arguments": {"path": "C:/input.png"}},
    )
    response_payload = _response(
        {
            "content": [
                {"type": "text", "text": '{"success":true}'},
                {"type": "image", "data": image_data, "mimeType": "image/png"},
            ],
            "isError": False,
        }
    )
    exact_body = json.dumps(response_payload, separators=(",", ":")).encode()

    async def app(scope, receive, send):
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": exact_body})

    incoming = [
        {
            "type": "http.request",
            "body": json.dumps(request_payload).encode(),
            "more_body": False,
        },
        {"type": "http.disconnect"},
    ]

    async def receive():
        return incoming.pop(0)

    sent = []

    async def send(message):
        sent.append(message)

    middleware = McpMethodAuditMiddleware(
        app,
        wire_audit_enabled=True,
        wire_audit_dir=tmp_path,
        wire_save_raw=True,
        wire_console_body=True,
        wire_validate=True,
    )

    with caplog.at_level(logging.INFO, logger="freecad_mcp.protocol"):
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": [
                    (b"mcp-protocol-version", b"2025-11-25"),
                    (b"mcp-session-id", b"test-session"),
                ],
            },
            receive,
            send,
        )

    response_files = list(Path(tmp_path).glob("*.response.json"))
    metadata_files = list(Path(tmp_path).glob("*.meta.json"))
    assert len(response_files) == 1
    assert len(metadata_files) == 1
    assert response_files[0].read_bytes() == exact_body

    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert metadata["response_body_sha256"]
    assert metadata["validation"]["response_valid"] is True
    assert "MCP wire body sent to client" in caplog.text
    assert image_data not in caplog.text
    assert "MCP specification validation" in caplog.text
    assert "response=PASS" in caplog.text


def test_parse_sse_framed_jsonrpc_response():
    body = b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
    messages = parse_jsonrpc_messages(body, "text/event-stream")
    assert messages == [{"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}]

@pytest.mark.asyncio
async def test_wire_audit_flags_empty_call_tool_result(tmp_path, caplog):
    """Reproduce the SaaS-side `{}` / missing CallToolResult.content failure."""
    request_payload = _request(
        "tools/call",
        params={"name": "open_image", "arguments": {"path": "C:/input.png"}},
    )
    broken_response = _response({})
    exact_body = json.dumps(broken_response, separators=(",", ":")).encode()

    async def app(scope, receive, send):
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": exact_body})

    incoming = [
        {
            "type": "http.request",
            "body": json.dumps(request_payload).encode(),
            "more_body": False,
        },
        {"type": "http.disconnect"},
    ]

    async def receive():
        return incoming.pop(0)

    async def send(message):
        return None

    middleware = McpMethodAuditMiddleware(
        app,
        wire_audit_enabled=True,
        wire_audit_dir=tmp_path,
        wire_save_raw=True,
        wire_console_body=True,
        wire_validate=True,
    )
    with caplog.at_level(logging.INFO, logger="freecad_mcp.protocol"):
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": [
                    (b"mcp-protocol-version", b"2025-11-25"),
                    (b"mcp-session-id", b"test-session"),
                ],
            },
            receive,
            send,
        )

    metadata_path = next(Path(tmp_path).glob("*.meta.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["validation"]["response_valid"] is False
    assert any(
        "result.content is required" in item
        for item in metadata["validation"]["response_errors"]
    )
    assert "response=FAIL" in caplog.text
