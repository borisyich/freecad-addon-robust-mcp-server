"""Validate a running remote FreeCAD MCP endpoint across stable HTTP revisions.

Live Streamable HTTP checks are run for 2025-03-26, 2025-06-18, and
2025-11-25.  MCP 2024-11-05 used the older HTTP+SSE transport, so that revision
is covered by the unit-level CallToolResult shape tests rather than being
misrepresented as a Streamable HTTP compatibility test.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

from freecad_mcp.protocol_audit import (
    first_header,
    validate_jsonrpc_exchange,
)

LIVE_HTTP_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("MCP_URL"))
    parser.add_argument("--token", default=os.environ.get("FREECAD_ACCESS_TOKEN"))
    parser.add_argument("--tool", default="list_documents")
    return parser.parse_args()


def require(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def headers_to_dict(headers: httpx.Headers) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name, value in headers.multi_items():
        result.setdefault(name.lower(), []).append(value)
    return result


def post_json(
    client: httpx.Client,
    url: str,
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
    protocol_version: str | None = None,
) -> tuple[httpx.Response, list[Any]]:
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    if protocol_version:
        headers["mcp-protocol-version"] = protocol_version
    response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    if not response.content:
        return response, []
    return response, [response.json()]


def run_revision(client: httpx.Client, url: str, requested_version: str, tool: str) -> None:
    print(f"\n=== MCP {requested_version} ===")
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": requested_version,
            "capabilities": {},
            "clientInfo": {"name": "freecad-protocol-verifier", "version": "1.0"},
        },
    }
    response, messages = post_json(client, url, initialize)
    response_headers = headers_to_dict(response.headers)
    report = validate_jsonrpc_exchange(
        request=initialize,
        response_messages=messages,
        protocol_version=requested_version,
        request_headers={},
        http_status=response.status_code,
    )
    if not report.response_valid:
        raise AssertionError(report.to_dict())

    negotiated = messages[0]["result"]["protocolVersion"]
    session_id = first_header(response_headers, "mcp-session-id")
    print(f"Negotiated: {negotiated}")
    print(f"Session: {session_id}")

    initialized = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    response, messages = post_json(
        client,
        url,
        initialized,
        session_id=session_id,
        protocol_version=negotiated if negotiated >= "2025-06-18" else None,
    )
    notification_report = validate_jsonrpc_exchange(
        request=initialized,
        response_messages=messages,
        protocol_version=negotiated,
        request_headers=(
            {"mcp-protocol-version": [negotiated]}
            if negotiated >= "2025-06-18"
            else {}
        ),
        http_status=response.status_code,
    )
    if not notification_report.valid:
        raise AssertionError(notification_report.to_dict())

    list_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    response, messages = post_json(
        client,
        url,
        list_request,
        session_id=session_id,
        protocol_version=negotiated if negotiated >= "2025-06-18" else None,
    )
    tools_report = validate_jsonrpc_exchange(
        request=list_request,
        response_messages=messages,
        protocol_version=negotiated,
        request_headers=(
            {"mcp-protocol-version": [negotiated]}
            if negotiated >= "2025-06-18"
            else {}
        ),
        http_status=response.status_code,
    )
    if not tools_report.valid:
        raise AssertionError(tools_report.to_dict())
    tools = messages[0]["result"]["tools"]
    tool_definition = next(item for item in tools if item["name"] == tool)
    print(f"Tools: {len(tools)}")

    call_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": tool, "arguments": {}},
    }
    response, messages = post_json(
        client,
        url,
        call_request,
        session_id=session_id,
        protocol_version=negotiated if negotiated >= "2025-06-18" else None,
    )
    call_report = validate_jsonrpc_exchange(
        request=call_request,
        response_messages=messages,
        protocol_version=negotiated,
        request_headers=(
            {"mcp-protocol-version": [negotiated]}
            if negotiated >= "2025-06-18"
            else {}
        ),
        tool_definition=tool_definition,
        http_status=response.status_code,
    )
    print(json.dumps(call_report.to_dict(), ensure_ascii=False, indent=2))
    if not call_report.valid:
        raise AssertionError(call_report.to_dict())

    if session_id:
        delete_headers = {"mcp-session-id": session_id}
        if negotiated >= "2025-06-18":
            delete_headers["mcp-protocol-version"] = negotiated
        client.delete(url, headers=delete_headers)


def main() -> None:
    args = parse_args()
    url = require(args.url, "--url or MCP_URL")
    token = require(args.token, "--token or FREECAD_ACCESS_TOKEN")
    with httpx.Client(
        headers={"authorization": f"Bearer {token}"},
        timeout=60.0,
        follow_redirects=True,
    ) as client:
        for version in LIVE_HTTP_VERSIONS:
            run_revision(client, url, version, args.tool)
    print("\nALL LIVE MCP PROTOCOL CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PROTOCOL CHECK FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
