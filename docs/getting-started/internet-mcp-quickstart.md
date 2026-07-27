# Internet-Accessible FreeCAD MCP Server

This guide exposes the local FreeCAD MCP server through a stable public HTTPS URL protected by a fixed Bearer token.

## Architecture

```text
SaaS agent
  -> HTTPS + Authorization: Bearer <token>
  -> Tailscale Funnel
  -> http://127.0.0.1:8000/mcp
  -> FreeCAD MCP server
  -> FreeCAD XML-RPC bridge on 127.0.0.1:9875
```

A static public IP, router port forwarding, and DDNS are not required. The computer creates the outbound Tailscale connection, so a changing ISP address does not affect the MCP URL.

## Prerequisites

- FreeCAD with the Robust MCP Bridge running
- Python project installed with `uv`
- Tailscale installed, signed in, and available in `PATH`
- Tailscale Funnel enabled for the device

## 1. Generate the access token

From the project directory, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\generate_access_token.ps1
```

The script saves `FREECAD_ACCESS_TOKEN` in the current Windows user's environment and prints it once. Store the token in the SaaS platform's secret storage. Do not commit it to Git or place it in configuration files.

## 2. Start FreeCAD and the local MCP server

Start FreeCAD and enable the Robust MCP XML-RPC Bridge. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_remote_mcp.ps1
```

The script:

- reads the saved Bearer token;
- detects the device's Tailscale DNS name;
- allows that hostname in the MCP Host/Origin validation;
- connects to FreeCAD through `127.0.0.1:9875`;
- starts Streamable HTTP on `127.0.0.1:8000/mcp`.

The MCP server remains bound to localhost and must not be exposed by router port forwarding.

If automatic hostname detection fails, save the hostname manually, without `https://` or `/mcp`:

```powershell
[Environment]::SetEnvironmentVariable(
    'FREECAD_PUBLIC_HOST',
    'freecad-agent.example-tailnet.ts.net',
    [EnvironmentVariableTarget]::User
)
```

## 3. Publish the server with Tailscale Funnel

Run in an elevated PowerShell window:

```powershell
tailscale funnel --bg http://127.0.0.1:8000
```

Check the published URL:

```powershell
tailscale funnel status
```

The final MCP endpoint is:

```text
https://<device>.<tailnet>.ts.net/mcp
```

## 4. Configure the SaaS MCP client

Use Streamable HTTP and pass the token as an HTTP Bearer credential:

```json
{
  "url": "https://<device>.<tailnet>.ts.net/mcp",
  "transport": "streamable-http",
  "headers": {
    "Authorization": "Bearer ${FREECAD_MCP_TOKEN}"
  }
}
```

Set `FREECAD_MCP_TOKEN` in the SaaS platform's secret storage to the value generated in step 1.

## 5. Basic checks

A request without the token should return `401 Unauthorized`:

```powershell
curl.exe -i "https://<device>.<tailnet>.ts.net/mcp"
```

A request without the token should NOT return `401 Unauthorized`:

```powershell
curl.exe -i `
>>   -H "Authorization: Bearer $env:FREECAD_ACCESS_TOKEN" `
>>   "https://freecad-agent.your-tailnet.ts.net/mcp"
```

Confirm that the local services are running:

```powershell
Test-NetConnection 127.0.0.1 -Port 9875
Test-NetConnection 127.0.0.1 -Port 8000
```

## Stop public access

Disable Funnel without stopping the local MCP server:

```powershell
tailscale funnel reset
```

Stop the `freecad-mcp` PowerShell process to stop the MCP server itself.

## Security note

The token grants access to all exposed MCP tools, including powerful tools such as `execute_python` and macro execution. Treat it as an administrator credential, rotate it after any suspected disclosure, and do not expose ports `8000`, `9875`, or `9876` directly to the LAN or Internet.
