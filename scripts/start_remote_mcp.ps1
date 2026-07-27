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
$env:FREECAD_TRANSPORT = 'http'
$env:FREECAD_HTTP_HOST = '127.0.0.1'
$env:FREECAD_HTTP_PORT = '8000'

uv run freecad-mcp
