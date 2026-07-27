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
