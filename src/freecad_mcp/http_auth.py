"""Minimal fixed Bearer-token authentication for HTTP MCP transport."""

from __future__ import annotations

import json
import secrets
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
