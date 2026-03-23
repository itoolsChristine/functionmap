# uninstall.ps1 -- Functionmap uninstaller for Windows PowerShell
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$HomeDir     = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
$ClaudeDir   = Join-Path $HomeDir ".claude"
$ToolsDir    = Join-Path $ClaudeDir "tools\functionmap"
$CommandsDir = Join-Path $ClaudeDir "commands"
$DocsDir     = Join-Path $ClaudeDir "docs"
$MapsDir     = Join-Path $ClaudeDir "functionmap"
$McpDir      = Join-Path $ClaudeDir "functionmap-mcp"
$ClaudeMd    = Join-Path $ClaudeDir "CLAUDE.md"
$ClaudeJson  = Join-Path $HomeDir ".claude.json"

# ============================================================================
#  Banner
# ============================================================================

Write-Host ""
Write-Host "  ============================================================"
Write-Host "    FUNCTIONMAP UNINSTALLER"
Write-Host "  ============================================================"
Write-Host ""

function Write-Info { param([string]$Msg) Write-Host "  [INFO]  $Msg" }
function Write-Ok   { param([string]$Msg) Write-Host "  [OK]    $Msg" }
function Write-Warn { param([string]$Msg) Write-Host "  [WARN]  $Msg" -ForegroundColor Yellow }

# ============================================================================
#  Confirm before proceeding
# ============================================================================

$hasTools    = Test-Path $ToolsDir
$hasCmds     = (Test-Path (Join-Path $CommandsDir "functionmap.md")) -or (Test-Path (Join-Path $CommandsDir "functionmap-update.md"))
$hasDocs     = (Test-Path (Join-Path $DocsDir "functionmap-help.md")) -or (Test-Path (Join-Path $DocsDir "functionmap-mcp.md"))
$hasMcp      = Test-Path $McpDir
$hasClaudeMd = Test-Path $ClaudeMd
$hasMaps     = (Test-Path $MapsDir) -and (Get-ChildItem $MapsDir -ErrorAction SilentlyContinue | Select-Object -First 1)

if (-not $hasTools -and -not $hasCmds -and -not $hasDocs -and -not $hasMcp) {
    Write-Info "Functionmap does not appear to be installed. Nothing to uninstall."
    exit 0
}

Write-Host "  This will uninstall functionmap."
Write-Host ""
Write-Host "  The following will be backed up before removal:"
if ($hasTools)    { Write-Host "    - Python tools ($ToolsDir)" }
if ($hasCmds)     { Write-Host "    - Skill commands (functionmap.md, functionmap-update.md)" }
if ($hasDocs)     { Write-Host "    - Help documentation (functionmap-help.md)" }
if ($hasMcp)      { Write-Host "    - MCP server ($McpDir)" }
if ($hasClaudeMd) { Write-Host "    - CLAUDE.md (functionmap sentinel blocks will be removed)" }
if ($hasMaps)     { Write-Host "    - Generated function maps ($MapsDir)" }
Write-Host ""
Write-Host "  Your generated function maps will NOT be deleted unless you choose to."
Write-Host ""

try {
    $answer = Read-Host "  Continue? [y/N]"
} catch {
    $answer = "y"
    Write-Info "Non-interactive mode: proceeding automatically"
}

if ($answer -notmatch "^[yY]") {
    Write-Host ""
    Write-Info "Uninstall cancelled."
    exit 0
}

# ============================================================================
#  Pre-uninstall backup (snapshot everything before deletion)
# ============================================================================

$BackupDir = ""
$hasExisting = (Test-Path $ToolsDir) -or
    (Test-Path (Join-Path $CommandsDir "functionmap.md")) -or
    (Test-Path (Join-Path $CommandsDir "functionmap-update.md")) -or
    (Test-Path (Join-Path $DocsDir "functionmap-help.md")) -or
    (Test-Path (Join-Path $DocsDir "functionmap-mcp.md")) -or
    (Test-Path $McpDir)

if ($hasExisting) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $BackupDir = Join-Path $ClaudeDir ".functionmap-backup-$timestamp"
    New-Item -ItemType Directory -Path "$BackupDir\tools" -Force | Out-Null
    New-Item -ItemType Directory -Path "$BackupDir\commands" -Force | Out-Null
    New-Item -ItemType Directory -Path "$BackupDir\docs" -Force | Out-Null

    if (Test-Path $ToolsDir) {
        Get-ChildItem $ToolsDir -File | ForEach-Object { Copy-Item $_.FullName "$BackupDir\tools\$($_.Name)" -Force }
    }
    foreach ($f in @("functionmap.md", "functionmap-update.md")) {
        $src = Join-Path $CommandsDir $f
        if (Test-Path $src) { Copy-Item $src "$BackupDir\commands\$f" -Force }
    }
    foreach ($f in @("functionmap-help.md", "functionmap-mcp.md")) {
        $src = Join-Path $DocsDir $f
        if (Test-Path $src) { Copy-Item $src "$BackupDir\docs\$f" -Force }
    }
    # Back up MCP server
    if (Test-Path $McpDir) {
        New-Item -ItemType Directory -Path "$BackupDir\mcp" -Force | Out-Null
        Get-ChildItem $McpDir -File | ForEach-Object { Copy-Item $_.FullName "$BackupDir\mcp\$($_.Name)" -Force }
    }

    if (Test-Path $ClaudeMd) { Copy-Item $ClaudeMd "$BackupDir\CLAUDE.md" -Force }

    # Back up generated function maps
    if ((Test-Path $MapsDir) -and (Get-ChildItem $MapsDir -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        Copy-Item $MapsDir "$BackupDir\functionmap" -Recurse -Force
        Write-Ok "Function maps backed up"
    }

    Write-Ok "Pre-uninstall backup created: $BackupDir"
} else {
    Write-Info "No existing files found to back up"
}

# ============================================================================
#  Remove installed files
# ============================================================================

# Tools directory (entire folder)
if (Test-Path $ToolsDir) {
    Remove-Item $ToolsDir -Recurse -Force
    Write-Ok "Removed $ToolsDir"
} else {
    Write-Info "Tools directory not found (already removed?)"
}

# Skill commands
foreach ($f in @("functionmap.md", "functionmap-update.md")) {
    $target = Join-Path $CommandsDir $f
    if (Test-Path $target) {
        Remove-Item $target -Force
        Write-Ok "Removed $target"
    }
}

# Help docs
foreach ($f in @("functionmap-help.md", "functionmap-mcp.md")) {
    $target = Join-Path $DocsDir $f
    if (Test-Path $target) {
        Remove-Item $target -Force
        Write-Ok "Removed $target"
    }
}

# MCP server
if (Test-Path $McpDir) {
    Remove-Item $McpDir -Recurse -Force
    Write-Ok "Removed $McpDir"
} else {
    Write-Info "MCP server directory not found (already removed?)"
}

# Deregister from .claude.json
if (Test-Path $ClaudeJson) {
    try {
        $jsonContent = Get-Content $ClaudeJson -Raw | ConvertFrom-Json
        if ($jsonContent.mcpServers -and $jsonContent.mcpServers.functionmap) {
            $jsonContent.mcpServers.PSObject.Properties.Remove("functionmap")
            $jsonContent | ConvertTo-Json -Depth 10 | Set-Content $ClaudeJson -Encoding UTF8
            Write-Ok "MCP server deregistered from .claude.json"
        }
    } catch {
        Write-Warn "Failed to update .claude.json: $_"
    }
}

# ============================================================================
#  Remove sentinel blocks from CLAUDE.md
# ============================================================================

if (Test-Path $ClaudeMd) {
    # Create backup
    Copy-Item $ClaudeMd "$ClaudeMd.bak" -Force
    Write-Info "Backup created: CLAUDE.md.bak"

    $content = [System.IO.File]::ReadAllText($ClaudeMd)
    $modified = $false

    # Remove INSTRUCTIONS block (inclusive of sentinels + surrounding blank lines)
    $instrPattern = "(?s)\r?\n?<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->.*?<!-- FUNCTIONMAP:INSTRUCTIONS:END -->\r?\n?"
    if ($content -match "FUNCTIONMAP:INSTRUCTIONS:BEGIN") {
        $content = [regex]::Replace($content, $instrPattern, "`n")
        $modified = $true
        Write-Ok "Removed instructions block from CLAUDE.md"
    }

    # Remove REGISTRY block (inclusive of sentinels + surrounding blank lines)
    $regPattern = "(?s)\r?\n?<!-- FUNCTIONMAP:BEGIN -->.*?<!-- FUNCTIONMAP:END -->\r?\n?"
    if ($content -match "FUNCTIONMAP:BEGIN") {
        $content = [regex]::Replace($content, $regPattern, "`n")
        $modified = $true
        Write-Ok "Removed registry block from CLAUDE.md"
    }

    # Clean trailing whitespace
    if ($modified) {
        $content = $content.TrimEnd() + "`n"
        [System.IO.File]::WriteAllText($ClaudeMd, $content)
    }
} else {
    Write-Info "No CLAUDE.md found (nothing to clean)"
}

# ============================================================================
#  Prompt for function map data removal
# ============================================================================

if (Test-Path $MapsDir) {
    Write-Host ""
    try {
        $answer = Read-Host "  Remove generated function maps ($MapsDir)? [y/N]"
    } catch {
        # Non-interactive -- default to No
        $answer = "n"
        Write-Info "Non-interactive mode: keeping generated function maps"
    }

    if ($answer -match "^[yY]") {
        Remove-Item $MapsDir -Recurse -Force
        Write-Ok "Removed $MapsDir"
    } else {
        Write-Info "Kept $MapsDir (your generated maps are preserved)"
    }
}

# ============================================================================
#  Done
# ============================================================================

Write-Host ""
Write-Host "  ============================================================"
Write-Host "    FUNCTIONMAP UNINSTALLED"
Write-Host "  ============================================================"
Write-Host ""
Write-Host "    Restart Claude Code to complete the removal."
if ($BackupDir) {
    Write-Host ""
    Write-Host "    Backup of removed files: $BackupDir"
    Write-Host "    (Safe to delete once you've confirmed the uninstall is correct)"
}
Write-Host ""
