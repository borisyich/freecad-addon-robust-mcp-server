# Internet-Accessible FreeCAD MCP Server

> **Two-component installation:** The external MCP server runs from this repository, while the bridge workbench runs inside FreeCAD from its installed `Mod\FreecadRobustMCPBridge` directory. Changes under `freecad/RobustMCPBridge` require updating that exact installed workbench and restarting FreeCAD. See [`COMPONENTS_AND_UPDATE.md`](../../COMPONENTS_AND_UPDATE.md).


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
- the Robust MCP Bridge addon from the same archive/version as the MCP server
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

When upgrading from an older archive, close FreeCAD and update the bundled
FreeCAD-side workbench first:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_freecad_bridge.ps1
```

Start FreeCAD and enable the Robust MCP XML-RPC Bridge. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_remote_mcp.ps1
```

The script:

- reads the saved Bearer token;
- detects the device's Tailscale DNS name;
- allows that hostname in the MCP Host/Origin validation;
- refuses to start if port `8000` is already occupied;
- performs an XML-RPC transport ping;
- verifies that FreeCAD's main-thread GUI execution queue responds;
- connects to FreeCAD through `127.0.0.1:9875`;
- starts Streamable HTTP on `127.0.0.1:8000/mcp`.

The public HTTP endpoint is started only after the preflight succeeds. A live
port `9875` alone is not sufficient: the FreeCAD Qt timer must also be able to
process queued CAD operations.

Remote mode also requires the timeout-aware XML-RPC method
`execute_with_timeout`. If preflight reports that this method is missing,
update/reinstall `freecad/RobustMCPBridge`, restart FreeCAD, and start MCP Bridge
again. This prevents timed-out cloud requests from remaining active for the
legacy fixed 30-second XML-RPC window.

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

A request with the token should not return `401 Unauthorized`. An authenticated
`GET /mcp` may remain open as an SSE stream, so always use a timeout for this
basic check:

```powershell
curl.exe -i --max-time 10 `
  -H "Authorization: Bearer $env:FREECAD_ACCESS_TOKEN" `
  "https://freecad-agent.your-tailnet.ts.net/mcp"
```

Confirm that the local services are running:

```powershell
Test-NetConnection 127.0.0.1 -Port 9875
Test-NetConnection 127.0.0.1 -Port 8000
```

For each MCP request, the server logs both the start and completion, including
the method, tool/resource target, HTTP status, and duration. For example:

```text
MCP request started: method=tools/call target=create_document
MCP request completed: method=tools/call target=create_document status=200 duration_ms=84.2
```

If startup reports that XML-RPC is reachable but the GUI execution queue is not
responding, stop and restart **MCP Bridge inside FreeCAD**, then rerun
`start_remote_mcp.ps1`.

## Stop public access

Disable Funnel without stopping the local MCP server:

```powershell
tailscale funnel reset
```

Stop the `freecad-mcp` PowerShell process to stop the MCP server itself.

## Security note

The token grants access to all exposed MCP tools, including powerful tools such as `execute_python` and macro execution. Treat it as an administrator credential, rotate it after any suspected disclosure, and do not expose ports `8000`, `9875`, or `9876` directly to the LAN or Internet.
