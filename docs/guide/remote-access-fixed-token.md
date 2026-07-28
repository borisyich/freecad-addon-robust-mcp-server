# Remote access with a fixed Bearer token

This profile exposes the Streamable HTTP MCP endpoint only on the loopback
interface and requires one fixed machine-to-machine token.

## Start the local MCP endpoint

Generate and store a token:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\generate_access_token.ps1
```

Open a new PowerShell window, start FreeCAD and its Robust MCP Bridge, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_remote_mcp.ps1
```

The startup script performs a mandatory bridge preflight before opening port
`8000`. It verifies both the XML-RPC endpoint and the FreeCAD GUI execution
queue. If the queue probe fails, restart MCP Bridge inside FreeCAD and rerun the
script.

The FreeCAD-side addon must come from the same updated archive. Remote startup
requires the `execute_with_timeout` XML-RPC method and intentionally refuses an
older bridge implementation.

The local endpoint is:

```text
http://127.0.0.1:8000/mcp
```

Every HTTP request must contain:

```http
Authorization: Bearer <FREECAD_ACCESS_TOKEN>
```

Do not pass the token as a command-line argument. Store it in the SaaS secret
manager and send it only in the `Authorization` header.

## Publish without port forwarding

For the simplest stable public URL without purchasing a domain, install
Tailscale and publish the local service with Funnel:

```powershell
tailscale funnel --bg http://127.0.0.1:8000
```

Use the reported HTTPS hostname plus `/mcp` as the SaaS MCP URL.
