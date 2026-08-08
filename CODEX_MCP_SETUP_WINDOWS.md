# Connect FreeCAD MCP to Codex on Windows

This setup connects Codex to the Robust MCP Bridge running inside the FreeCAD GUI:

```text
Codex -> freecad-mcp (STDIO) -> XML-RPC localhost:9875 -> FreeCAD
```

## 1. Start the bridge in FreeCAD

1. Open FreeCAD and switch to the **Robust MCP Bridge** workbench.
2. Click **Start MCP Bridge**, or select **MCP Bridge -> Start Bridge**.
3. Keep FreeCAD running. Its console should report that XML-RPC is listening on `localhost:9875`.

## 2. Verify the bridge connection

Run the following in PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& "path\to\freecad-addon-robust-mcp-server\.venv\Scripts\freecad-mcp.exe" `
    --check `
    --mode xmlrpc
```

The command should report `Connection successful!` and show the FreeCAD version.

## 3. Configure Codex

Add the following to `path\to\.codex\config.toml`:

```toml
[mcp_servers.freecad-mcp]
enabled = true
required = false
command = 'path\to\freecad-addon-robust-mcp-server\.venv\Scripts\freecad-mcp.exe'
args = ["--mode", "xmlrpc", "--transport", "stdio"]
cwd = 'path\to\freecad-addon-robust-mcp-server'
startup_timeout_sec = 30
tool_timeout_sec = 120

[mcp_servers.freecad-mcp.env]
FREECAD_MODE = "xmlrpc"
FREECAD_SOCKET_HOST = "localhost"
FREECAD_XMLRPC_PORT = "9875"
PYTHONUTF8 = "1"
PYTHONIOENCODING = "utf-8"
```

Use the virtual-environment executable directly. Do not put a complete shell command in `command`; pass command-line options through `args`.

## 4. Restart and verify Codex

1. Keep FreeCAD and its MCP bridge running.
2. Restart Codex and open a new task so it reloads the MCP configuration.
3. Run `codex mcp list`, or use `/mcp` in a supported Codex interface.
4. Confirm that `freecad-mcp` is enabled and its tools are available.

If Codex reports a connection error, verify that the FreeCAD bridge is still running on port `9875`. If Python fails while printing check marks on a non-UTF-8 Windows console, keep the two UTF-8 environment variables shown above.

For the supported Codex MCP configuration format, see the [official OpenAI documentation](https://developers.openai.com/codex/mcp).
