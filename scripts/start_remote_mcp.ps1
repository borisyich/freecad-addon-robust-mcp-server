$ErrorActionPreference = 'Stop'

# PowerShell/Windows Terminal/VS Code can keep a long-lived parent process with
# stale environment variables. Read the persisted per-user value directly as a
# fallback instead of relying only on the inherited process environment.
$token = $env:FREECAD_ACCESS_TOKEN
if ([string]::IsNullOrWhiteSpace($token)) {
    $token = [Environment]::GetEnvironmentVariable(
        'FREECAD_ACCESS_TOKEN',
        [EnvironmentVariableTarget]::User
    )
}

if ([string]::IsNullOrWhiteSpace($token)) {
    throw @'
FREECAD_ACCESS_TOKEN was not found in either the current process or the Windows user environment.
Run scripts\generate_access_token.ps1, or set it manually with:
[Environment]::SetEnvironmentVariable('FREECAD_ACCESS_TOKEN', '<TOKEN>', 'User')
'@
}

# Make the resolved persisted value available to the MCP child process.
$env:FREECAD_ACCESS_TOKEN = $token


# Resolve the stable public hostname used by Tailscale Funnel. The MCP SDK
# validates Host/Origin headers to prevent DNS rebinding, so the *.ts.net name
# must be explicitly allow-listed before the Python process starts.
$publicHost = $env:FREECAD_PUBLIC_HOST
if ([string]::IsNullOrWhiteSpace($publicHost)) {
    $publicHost = [Environment]::GetEnvironmentVariable(
        'FREECAD_PUBLIC_HOST',
        [EnvironmentVariableTarget]::User
    )
}

if ([string]::IsNullOrWhiteSpace($publicHost)) {
    $tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($null -ne $tailscale) {
        try {
            $tailscaleStatus = (& tailscale status --json | Out-String) | ConvertFrom-Json
            $publicHost = [string]$tailscaleStatus.Self.DNSName
        }
        catch {
            Write-Warning "Could not detect Tailscale DNS name: $($_.Exception.Message)"
        }
    }
}

if ([string]::IsNullOrWhiteSpace($publicHost)) {
    throw @'
FREECAD_PUBLIC_HOST is not set and the Tailscale DNS name could not be detected.
Set it to the hostname only, without https:// or /mcp, for example:
[Environment]::SetEnvironmentVariable('FREECAD_PUBLIC_HOST', 'freecad-agent.example.ts.net', 'User')
'@
}

$publicHost = $publicHost.Trim().TrimEnd('.')
if ($publicHost.Contains('://') -or $publicHost.Contains('/')) {
    throw 'FREECAD_PUBLIC_HOST must contain only the hostname, without https:// or /mcp.'
}
$env:FREECAD_PUBLIC_HOST = $publicHost
Write-Host "Allowed public MCP host: $publicHost"

$env:FREECAD_MODE = 'xmlrpc'
$env:FREECAD_SOCKET_HOST = '127.0.0.1'
$env:FREECAD_XMLRPC_PORT = '9875'
$env:FREECAD_REQUIRE_BOUNDED_XMLRPC = 'true'
$env:FREECAD_TRANSPORT = 'http'
$env:FREECAD_HTTP_HOST = '127.0.0.1'
$env:FREECAD_HTTP_PORT = '8000'

$existingListener = Get-NetTCPConnection `
    -LocalPort ([int]$env:FREECAD_HTTP_PORT) `
    -State Listen `
    -ErrorAction SilentlyContinue

if ($null -ne $existingListener) {
    $listenerDetails = $existingListener |
        Select-Object -First 1 |
        ForEach-Object {
            $processName = 'unknown'
            try {
                $processName = (
                    Get-Process -Id $_.OwningProcess -ErrorAction Stop
                ).ProcessName
            }
            catch {
                $processName = 'unknown'
            }
            "PID=$($_.OwningProcess), process=$processName"
        }
    throw "Port $env:FREECAD_HTTP_PORT is already in use ($listenerDetails). Stop the old MCP server before starting a new one."
}

Write-Host 'Running FreeCAD bridge preflight...'
Write-Host '  1. XML-RPC transport ping'
Write-Host '  2. FreeCAD GUI execution-queue probe'
Write-Host '  3. Optional bounded version lookup'

& uv run freecad-mcp `
    --check `
    --mode xmlrpc `
    --host $env:FREECAD_SOCKET_HOST `
    --port ([int]$env:FREECAD_XMLRPC_PORT)

if ($LASTEXITCODE -ne 0) {
    throw @'
FreeCAD bridge preflight failed. The public HTTP MCP server was not started.

Check the following:
1. FreeCAD GUI is running.
2. Robust MCP Bridge is started inside FreeCAD.
3. Port 9875 belongs to the current FreeCAD process.
4. If XML-RPC ping succeeds but the queue probe fails, restart MCP Bridge inside FreeCAD.
'@
}

Write-Host 'Preflight passed. Starting authenticated HTTP MCP server...'
& uv run freecad-mcp
