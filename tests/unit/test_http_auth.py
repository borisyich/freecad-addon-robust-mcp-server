"""Tests for fixed Bearer-token ASGI middleware."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = (
    Path(__file__).parents[2] / "src" / "freecad_mcp" / "http_auth.py"
)
SPEC = importlib.util.spec_from_file_location("freecad_mcp_http_auth", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
StaticBearerAuthMiddleware = MODULE.StaticBearerAuthMiddleware
McpMethodAuditMiddleware = MODULE.McpMethodAuditMiddleware


@pytest.mark.asyncio
async def test_rejects_missing_token_header():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    middleware = StaticBearerAuthMiddleware(app, "x" * 64)
    messages: list[dict[str, Any]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await middleware(
        {"type": "http", "headers": [], "method": "POST", "path": "/mcp"},
        receive,
        send,
    )

    assert called is False
    assert messages[0]["status"] == 401


@pytest.mark.asyncio
async def test_accepts_exact_bearer_token():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    token = "x" * 64
    middleware = StaticBearerAuthMiddleware(app, token)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    await middleware(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "method": "POST",
            "path": "/mcp",
        },
        receive,
        send,
    )

    assert called is True


def test_rejects_short_configured_token():
    async def app(scope, receive, send):
        return None

    with pytest.raises(ValueError, match="at least 32"):
        StaticBearerAuthMiddleware(app, "short")


@pytest.mark.asyncio
async def test_audit_middleware_forwards_real_disconnect_after_replayed_body():
    """The audit layer must not hide ASGI disconnect events from Streamable HTTP."""

    received_by_app: list[dict[str, Any]] = []

    async def app(scope, receive, send):
        received_by_app.append(await receive())
        received_by_app.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    incoming = [
        {
            "type": "http.request",
            "body": b'{"jsonrpc":"2.0","id":1,"method":"initialize"}',
            "more_body": False,
        },
        {"type": "http.disconnect"},
    ]

    async def receive():
        return incoming.pop(0)

    sent: list[dict[str, Any]] = []

    async def send(message):
        sent.append(message)

    middleware = McpMethodAuditMiddleware(app)
    await middleware(
        {"type": "http", "method": "POST", "path": "/mcp", "headers": []},
        receive,
        send,
    )

    assert received_by_app[0]["type"] == "http.request"
    assert received_by_app[1] == {"type": "http.disconnect"}
    assert sent[0]["status"] == 200
