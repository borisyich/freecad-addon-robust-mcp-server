# MCP wire audit and specification validation

The server has two distinct diagnostic layers:

1. `FreecadFastMCP.call_tool` logs the Python value returned by a tool before it
   is wrapped as a JSON-RPC response.
2. `McpMethodAuditMiddleware` records the final HTTP entity body emitted by the
   ASGI application. This is the JSON-RPC payload received by the SaaS MCP
   connector, before TLS and HTTP transfer framing.

## Runtime files

The remote startup script enables wire auditing and writes artifacts to:

```text
logs/mcp-wire/
```

Each POST request produces:

- `*.request.json` — exact JSON-RPC request body received by the server;
- `*.response.json` or `*.response.sse` — exact response entity body sent to
  the client;
- `*.meta.json` — HTTP status, safe headers, protocol version, session ID,
  byte counts, SHA-256 hashes, and validation results.

The raw response may contain complete base64-encoded images, local paths, model
metadata, and other sensitive data. Do not publish the audit directory without
reviewing it.

The console prints the final JSON-RPC structure with only image, audio, and blob
base64 replaced by length and SHA-256 markers. Text tool output is preserved.

## Important log lines

```text
MCP wire response: ... bytes=... sha256=... raw_body=...
MCP wire body sent to client (binary redacted only): {...}
MCP specification validation: ... request=PASS response=PASS ...
```

`request=FAIL` identifies a client-side protocol violation, such as a missing
`MCP-Protocol-Version` header after negotiation. `response=FAIL` identifies a
server response that does not satisfy the relevant MCP response shape.

## Protocol revisions covered

Unit tests validate tool-result shapes for these stable revisions:

- `2024-11-05` — legacy content-only result model, text/image/resource blocks;
- `2025-03-26` — Streamable HTTP and audio content;
- `2025-06-18` — structured tool output and `outputSchema`;
- `2025-11-25` — current stable revision and current tool-name guidance.

The `2026-07-28` specification is still a release candidate and substantially
changes the transport model. It is intentionally not claimed as supported by
this stateful FastMCP v1.x server.

## Tests

Run protocol unit tests:

```powershell
uv run pytest tests/unit/test_protocol_audit.py -q
```

Run the live remote endpoint matrix:

```powershell
$env:MCP_URL = "https://your-host.ts.net/mcp"
$env:FREECAD_ACCESS_TOKEN = [Environment]::GetEnvironmentVariable(
    "FREECAD_ACCESS_TOKEN",
    [EnvironmentVariableTarget]::User
)

uv run python .\scripts\verify_remote_mcp_protocol.py
```

The live script tests Streamable HTTP revisions `2025-03-26`, `2025-06-18`,
and `2025-11-25`, performs initialization, sends the initialized notification,
lists tools, calls `list_documents`, and validates the final responses.
