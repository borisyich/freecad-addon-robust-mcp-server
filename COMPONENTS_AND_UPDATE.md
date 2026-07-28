# FreeCAD MCP: Two Components and Development Updates

This repository contains two separate runtime components.

## 1. External MCP server

Runs as a normal Python process outside FreeCAD:

```text
src/freecad_mcp/
scripts/start_remote_mcp.ps1
.agents/
```

It provides MCP tools, resources, prompts, Skills routing, HTTP transport,
Bearer authentication, and the Tailscale-facing endpoint.

Run it from the repository checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_remote_mcp.ps1
```

Changes under `src/freecad_mcp`, `.agents`, `.clinerules`, and most documentation
do not require copying files into FreeCAD's `Mod` directory.

## 2. FreeCAD-side bridge workbench

Runs inside the FreeCAD process and owns local ports 9875 and 9876:

```text
freecad/RobustMCPBridge/
```

The installed addon normally has this layout:

```text
<FreeCAD Mod>/FreecadRobustMCPBridge/
  package.xml
  freecad/
    RobustMCPBridge/
      freecad_mcp_bridge/
        server.py
```

Changes to XML-RPC methods, the Qt execution queue, request cancellation,
bridge health checks, or screenshot implementation require updating this
installed workbench and restarting FreeCAD.

## Find the copy actually loaded by FreeCAD

Start the bridge, open **View > Panels > Python console**, and run:

```python
import freecad_mcp_bridge.server as bridge_server
print(bridge_server.__file__)
```

The printed path is the authoritative installed code path. Avoid keeping
multiple active copies of the workbench in different `Mod` directories.

## Update the existing installed workbench

Close FreeCAD completely, then run from this repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_freecad_bridge.ps1 `
  -Destination "C:\Program Files\FreeCAD 1.0\Mod\FreecadRobustMCPBridge"
```

Use the exact addon root printed or inferred from `bridge_server.__file__`.
The script updates that existing installation, creates a sibling backup, and
does not install a second copy under `%APPDATA%`.

An elevated PowerShell may be required when the destination is under
`C:\Program Files`.

## Verify the installed bridge protocol

After restarting FreeCAD and starting the bridge:

```powershell
@'
import xmlrpc.client
p = xmlrpc.client.ServerProxy("http://127.0.0.1:9875", allow_none=True)
methods = p.system.listMethods()
print("ping" in methods)
print("execute" in methods)
print("execute_with_timeout" in methods)
print("get_health" in methods)
'@ | uv run python -
```

All four lines should print `True` for the reliable remote version.

## Recommended development rule

Treat the repository checkout as the source of truth:

- edit tools, Skills, prompts, and HTTP code in the checkout;
- after changing `freecad/RobustMCPBridge`, update the installed workbench;
- restart FreeCAD after every workbench-side update;
- restart the external MCP server after server-side changes.
