param(
    [Parameter(Mandatory = $false)]
    [string]$Destination,

    [Parameter(Mandatory = $false)]
    [string]$BackupDirectory
)

$ErrorActionPreference = 'Stop'

$freecadProcesses = Get-Process -Name 'FreeCAD' -ErrorAction SilentlyContinue
if ($null -ne $freecadProcesses) {
    throw 'Close all FreeCAD processes before updating Robust MCP Bridge.'
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceCodeRoot = Join-Path $projectRoot 'freecad\RobustMCPBridge'
$sourceServer = Join-Path $sourceCodeRoot 'freecad_mcp_bridge\server.py'

if (-not (Test-Path -LiteralPath $sourceServer)) {
    throw "FreeCAD-side bridge source was not found: $sourceServer"
}

$sourceCode = Get-Content -LiteralPath $sourceServer -Raw
if (-not $sourceCode.Contains('execute_with_timeout')) {
    throw 'The bundled FreeCAD-side bridge does not contain execute_with_timeout.'
}

function Resolve-BridgeInstallation {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
    }
    catch {
        return $null
    }

    # Legacy layout used by the original wiki/manual package:
    # Mod\FreecadRobustMCPBridge\addon\FreecadRobustMCPBridge\...
    $legacyCodeRoot = Join-Path $fullPath 'addon\FreecadRobustMCPBridge'
    $legacyServer = Join-Path $legacyCodeRoot 'freecad_mcp_bridge\server.py'
    if (Test-Path -LiteralPath $legacyServer) {
        return [PSCustomObject]@{
            InstallRoot = $fullPath
            CodeRoot = $legacyCodeRoot
            ServerPath = $legacyServer
            Layout = 'legacy-addon'
        }
    }

    # Current namespace-package layout:
    # Mod\RobustMCPBridge\freecad\RobustMCPBridge\...
    $namespaceCodeRoot = Join-Path $fullPath 'freecad\RobustMCPBridge'
    $namespaceServer = Join-Path $namespaceCodeRoot 'freecad_mcp_bridge\server.py'
    if (Test-Path -LiteralPath $namespaceServer) {
        return [PSCustomObject]@{
            InstallRoot = $fullPath
            CodeRoot = $namespaceCodeRoot
            ServerPath = $namespaceServer
            Layout = 'namespace-package'
        }
    }

    # Also accept the active workbench code directory itself as -Destination.
    $directServer = Join-Path $fullPath 'freecad_mcp_bridge\server.py'
    if (Test-Path -LiteralPath $directServer) {
        return [PSCustomObject]@{
            InstallRoot = $fullPath
            CodeRoot = $fullPath
            ServerPath = $directServer
            Layout = 'direct-code-root'
        }
    }

    return $null
}

if ([string]::IsNullOrWhiteSpace($Destination)) {
    $candidatePaths = New-Object System.Collections.Generic.List[string]

    foreach ($name in @('FreecadRobustMCPBridge', 'RobustMCPBridge')) {
        $candidatePaths.Add((Join-Path $env:APPDATA "FreeCAD\Mod\$name"))
    }

    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ([string]::IsNullOrWhiteSpace($base) -or -not (Test-Path -LiteralPath $base)) {
            continue
        }

        Get-ChildItem -LiteralPath $base -Directory -Filter 'FreeCAD*' -ErrorAction SilentlyContinue |
            ForEach-Object {
                foreach ($name in @('FreecadRobustMCPBridge', 'RobustMCPBridge')) {
                    $candidatePaths.Add((Join-Path $_.FullName "Mod\$name"))
                }
            }
    }

    $resolvedCandidates = @(
        $candidatePaths |
            Select-Object -Unique |
            ForEach-Object { Resolve-BridgeInstallation -Path $_ } |
            Where-Object { $null -ne $_ }
    )

    if ($resolvedCandidates.Count -eq 1) {
        $installation = $resolvedCandidates[0]
    }
    elseif ($resolvedCandidates.Count -eq 0) {
        throw @'
The existing FreeCAD Robust MCP Bridge installation was not found automatically.
Run this script again with the exact installed addon root, for example:

powershell -ExecutionPolicy Bypass -File .\scripts\update_freecad_bridge.ps1 `
  -Destination "C:\Program Files\FreeCAD 1.0\Mod\FreecadRobustMCPBridge"

The script supports both:
  addon\FreecadRobustMCPBridge\freecad_mcp_bridge\server.py
  freecad\RobustMCPBridge\freecad_mcp_bridge\server.py
'@
    }
    else {
        $formatted = ($resolvedCandidates | ForEach-Object {
            "{0} ({1})" -f $_.InstallRoot, $_.Layout
        }) -join "`n  - "

        throw @"
Multiple Robust MCP Bridge installations were found:
  - $formatted

Specify the exact copy loaded by FreeCAD with -Destination.
"@
    }
}
else {
    $installation = Resolve-BridgeInstallation -Path $Destination
    if ($null -eq $installation) {
        $fullDestination = [System.IO.Path]::GetFullPath($Destination)
        throw @"
The destination is not a recognized existing Robust MCP Bridge installation:
$fullDestination

Expected one of:
  $fullDestination\addon\FreecadRobustMCPBridge\freecad_mcp_bridge\server.py
  $fullDestination\freecad\RobustMCPBridge\freecad_mcp_bridge\server.py
  $fullDestination\freecad_mcp_bridge\server.py
"@
    }
}

$installRoot = $installation.InstallRoot
$destinationCodeRoot = $installation.CodeRoot
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'

if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
    $BackupDirectory = Join-Path $env:LOCALAPPDATA 'FreeCAD\RobustMCPBridgeBackups'
}

$backupDirectoryFull = [System.IO.Path]::GetFullPath($BackupDirectory)
$modDirectory = Split-Path -Parent $installRoot

# Never place backups inside any FreeCAD Mod directory. FreeCAD recursively
# scans Mod children as addons and may import Python modules from a backup copy.
$modDirectoryWithSeparator = $modDirectory.TrimEnd('\') + '\'
$backupDirectoryWithSeparator = $backupDirectoryFull.TrimEnd('\') + '\'
if ($backupDirectoryWithSeparator.StartsWith(
        $modDirectoryWithSeparator,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw @"
BackupDirectory must be outside the FreeCAD Mod directory.
Mod directory:    $modDirectory
Backup directory: $backupDirectoryFull
"@
}

New-Item -ItemType Directory -Path $backupDirectoryFull -Force | Out-Null
$installFolderName = Split-Path -Leaf $installRoot
$backupRoot = Join-Path $backupDirectoryFull "$installFolderName-$timestamp"

Write-Host 'Updating the existing FreeCAD-side bridge:'
Write-Host "  Layout:      $($installation.Layout)"
Write-Host "  Source:      $sourceCodeRoot"
Write-Host "  Code target: $destinationCodeRoot"
Write-Host "  Backup:      $backupRoot"

# Back up the exact installation that FreeCAD currently loads.
Copy-Item -LiteralPath $installRoot -Destination $backupRoot -Recurse -Force

# Merge source files into the active code directory. Do not delete the target:
# legacy wiki packages may contain Init.py/InitGui.py wrappers that are not part
# of the repository's current namespace-package source tree.
# Do not overwrite package.xml: its subdirectory differs between layouts.
$robocopyArgs = @(
    $sourceCodeRoot,
    $destinationCodeRoot,
    '/E',
    '/R:2',
    '/W:1',
    '/NFL',
    '/NDL',
    '/NJH',
    '/NJS',
    '/NP'
)

& robocopy.exe @robocopyArgs | Out-Null
$robocopyExitCode = $LASTEXITCODE
if ($robocopyExitCode -ge 8) {
    throw "Robocopy failed with exit code $robocopyExitCode. The backup is at: $backupRoot"
}

$installedServer = Join-Path $destinationCodeRoot 'freecad_mcp_bridge\server.py'
$installedServerCode = Get-Content -LiteralPath $installedServer -Raw
if (-not $installedServerCode.Contains('execute_with_timeout')) {
    throw 'Post-copy verification failed: execute_with_timeout is missing from the installed bridge.'
}

Write-Host ''
Write-Host 'Existing FreeCAD Robust MCP Bridge installation updated successfully.'
Write-Host 'The installed package.xml and legacy launcher files were preserved.'
Write-Host 'The backup was stored outside every FreeCAD Mod directory.'
Write-Host 'No second workbench copy was created inside Mod.'
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Start FreeCAD.'
Write-Host '  2. Start MCP Bridge inside FreeCAD.'
Write-Host '  3. Confirm bridge_server.__file__ points to the same installation.'
Write-Host '  4. Verify execute_with_timeout with system.listMethods().'
Write-Host '  5. Run scripts\start_remote_mcp.ps1.'
