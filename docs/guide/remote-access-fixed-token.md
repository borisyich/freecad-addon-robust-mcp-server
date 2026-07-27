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
