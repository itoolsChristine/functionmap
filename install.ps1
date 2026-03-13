# install.ps1 -- Functionmap installer for Windows PowerShell
# Usage: irm https://raw.githubusercontent.com/itoolsChristine/functionmap/main/install.ps1 | iex
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

# ============================================================================
#  Constants
# ============================================================================

$RepoUrl    = "https://raw.githubusercontent.com/itoolsChristine/functionmap/main"
$HomeDir    = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
$ClaudeDir  = Join-Path $HomeDir ".claude"
$ToolsDir   = Join-Path $ClaudeDir "tools\functionmap"
$CommandsDir = Join-Path $ClaudeDir "commands"
$DocsDir    = Join-Path $ClaudeDir "docs"
$MapsDir    = Join-Path $ClaudeDir "functionmap"
$ClaudeMd   = Join-Path $ClaudeDir "CLAUDE.md"

$ToolFiles    = @("functionmap.py", "categorize.py", "quickmap.py", "thirdparty.py", "describe.py")
$CommandFiles = @("functionmap.md", "functionmap-update.md")
$DocFiles     = @("functionmap-help.md")

# ============================================================================
#  Banner
# ============================================================================

function Show-Banner {
    Write-Host ""
    Write-Host "  ============================================================"
    Write-Host "    FUNCTIONMAP INSTALLER"
    Write-Host "    Index every function so Claude finds before it builds."
    Write-Host "  ============================================================"
    Write-Host ""
}

# ============================================================================
#  Helpers
# ============================================================================

function Write-Info { param([string]$Msg) Write-Host "  [INFO]  $Msg" }
function Write-Ok   { param([string]$Msg) Write-Host "  [OK]    $Msg" }
function Write-Warn { param([string]$Msg) Write-Host "  [WARN]  $Msg" -ForegroundColor Yellow }
function Stop-Install { param([string]$Msg) Write-Host "  [ERROR] $Msg" -ForegroundColor Red; throw $Msg }

# ============================================================================
#  Pre-flight checks
# ============================================================================

function Test-Preflight {
    # Find Python
    $script:Python = $null
    $candidates = @("python3", "python")
    foreach ($cmd in $candidates) {
        try {
            $null = & $cmd --version 2>&1
            $script:Python = $cmd
            break
        } catch {
            continue
        }
    }

    if (-not $script:Python) {
        Stop-Install "Python not found. Install Python 3.8+ and ensure it is in your PATH."
    }

    # Verify version >= 3.8
    $pyVersion = & $script:Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
    $parts = $pyVersion.Split(".")
    $major = [int]$parts[0]
    $minor = [int]$parts[1]

    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
        Stop-Install "Python 3.8+ required (found $pyVersion). Please upgrade Python."
    }
    Write-Ok "Python $pyVersion ($script:Python)"

    # Check Claude Code directory
    if (-not (Test-Path $ClaudeDir)) {
        Stop-Install "$ClaudeDir does not exist. Install and run Claude Code at least once first."
    }
    Write-Ok "Claude Code directory exists"

    # Check write permissions
    try {
        $testFile = Join-Path $ClaudeDir ".install-test-$$"
        [System.IO.File]::WriteAllText($testFile, "test")
        Remove-Item $testFile -Force
    } catch {
        Stop-Install "No write permission to $ClaudeDir"
    }
    Write-Ok "Write permissions verified"
}

# ============================================================================
#  Determine source mode
# ============================================================================

function Get-SourceMode {
    $script:SourceMode = "remote"
    $script:ScriptRoot = ""

    # Detect if running from a cloned repo
    $invocation = $MyInvocation.PSCommandPath
    if (-not $invocation) {
        # Piped from irm | iex -- no PSCommandPath
        $invocation = ""
    }

    if ($invocation -and (Test-Path $invocation)) {
        $script:ScriptRoot = Split-Path $invocation -Parent
        $srcTools = Join-Path $script:ScriptRoot "src\tools"
        $srcCmds  = Join-Path $script:ScriptRoot "src\commands"
        if ((Test-Path $srcTools) -and (Test-Path $srcCmds)) {
            $script:SourceMode = "local"
        }
    }

    if ($script:SourceMode -eq "local") {
        Write-Info "Installing from local clone: $script:ScriptRoot"
    } else {
        Write-Info "Installing from GitHub: $RepoUrl"
    }
}

# ============================================================================
#  File retrieval
# ============================================================================

function Get-InstallFile {
    param(
        [string]$SrcRel,    # e.g. src/tools/functionmap.py
        [string]$Dest       # e.g. ~/.claude/tools/functionmap/functionmap.py
    )

    if ($script:SourceMode -eq "local") {
        $localPath = Join-Path $script:ScriptRoot $SrcRel.Replace("/", "\")
        if (-not (Test-Path $localPath)) {
            Stop-Install "Local file not found: $localPath"
        }
        Copy-Item $localPath $Dest -Force
    } else {
        $url = "$RepoUrl/$SrcRel"
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -ErrorAction Stop
            [System.IO.File]::WriteAllBytes($Dest, $response.Content)
        } catch {
            Stop-Install "Failed to download: $url"
        }
    }
}

# ============================================================================
#  Create directories
# ============================================================================

function Confirm-Install {
    $existingTools    = $false
    $existingCmds     = $false
    $existingDocs     = $false
    $existingClaudeMd = $false
    $existingMaps     = $false
    $script:IsUpgrade = $false

    foreach ($f in $ToolFiles) { if (Test-Path (Join-Path $ToolsDir $f)) { $existingTools = $true; break } }
    foreach ($f in $CommandFiles) { if (Test-Path (Join-Path $CommandsDir $f)) { $existingCmds = $true; break } }
    foreach ($f in $DocFiles) { if (Test-Path (Join-Path $DocsDir $f)) { $existingDocs = $true; break } }
    if (Test-Path $ClaudeMd) { $existingClaudeMd = $true }
    if ((Test-Path $MapsDir) -and (Get-ChildItem $MapsDir -ErrorAction SilentlyContinue | Select-Object -First 1)) { $existingMaps = $true }

    if ($existingTools -or $existingCmds -or $existingDocs) {
        $script:IsUpgrade = $true
    }

    Write-Host ""
    if ($script:IsUpgrade) {
        Write-Host "  Existing functionmap installation detected."
        Write-Host "  This will UPGRADE your installation."
    } else {
        Write-Host "  This will install functionmap."
    }

    Write-Host ""
    Write-Host "  The following will be backed up before any changes:"
    if ($existingTools)    { Write-Host "    - Python tools ($ToolsDir)" }
    if ($existingCmds)     { Write-Host "    - Skill commands (functionmap.md, functionmap-update.md)" }
    if ($existingDocs)     { Write-Host "    - Help documentation (functionmap-help.md)" }
    if ($existingClaudeMd) { Write-Host "    - CLAUDE.md (sentinel blocks will be updated, not replaced)" }
    if ($existingMaps)     { Write-Host "    - Generated function maps ($MapsDir)" }
    if (-not $existingTools -and -not $existingCmds -and -not $existingDocs -and -not $existingClaudeMd -and -not $existingMaps) {
        Write-Host "    (nothing to back up -- fresh install)"
    }

    Write-Host ""
    if ($script:IsUpgrade) {
        Write-Host "  Your existing function maps will NOT be erased."
    }

    Write-Host ""
    try {
        $answer = Read-Host "  Continue? [y/N]"
    } catch {
        # Non-interactive: proceed automatically
        $answer = "y"
        Write-Info "Non-interactive mode: proceeding automatically"
    }

    if ($answer -notmatch "^[yY]") {
        Write-Host ""
        Write-Info "Installation cancelled."
        exit 0
    }
}

# ============================================================================

function Backup-Existing {
    $script:BackupDir = ""
    $hasExisting = $false

    foreach ($f in $ToolFiles) { if (Test-Path (Join-Path $ToolsDir $f)) { $hasExisting = $true; break } }
    foreach ($f in $CommandFiles) { if (Test-Path (Join-Path $CommandsDir $f)) { $hasExisting = $true; break } }
    foreach ($f in $DocFiles) { if (Test-Path (Join-Path $DocsDir $f)) { $hasExisting = $true; break } }
    if (Test-Path $ClaudeMd) { $hasExisting = $true }

    if (-not $hasExisting) {
        Write-Info "Fresh install (no existing files to back up)"
        return
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $script:BackupDir = Join-Path $ClaudeDir ".functionmap-backup-$timestamp"
    New-Item -ItemType Directory -Path "$script:BackupDir\tools" -Force | Out-Null
    New-Item -ItemType Directory -Path "$script:BackupDir\commands" -Force | Out-Null
    New-Item -ItemType Directory -Path "$script:BackupDir\docs" -Force | Out-Null

    foreach ($f in $ToolFiles) {
        $src = Join-Path $ToolsDir $f
        if (Test-Path $src) { Copy-Item $src "$script:BackupDir\tools\$f" -Force }
    }
    $vFile = Join-Path $ToolsDir ".version"
    if (Test-Path $vFile) { Copy-Item $vFile "$script:BackupDir\tools\.version" -Force }

    foreach ($f in $CommandFiles) {
        $src = Join-Path $CommandsDir $f
        if (Test-Path $src) { Copy-Item $src "$script:BackupDir\commands\$f" -Force }
    }

    foreach ($f in $DocFiles) {
        $src = Join-Path $DocsDir $f
        if (Test-Path $src) { Copy-Item $src "$script:BackupDir\docs\$f" -Force }
    }

    if (Test-Path $ClaudeMd) { Copy-Item $ClaudeMd "$script:BackupDir\CLAUDE.md" -Force }

    # Back up generated function maps
    if ((Test-Path $MapsDir) -and (Get-ChildItem $MapsDir -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        Copy-Item $MapsDir "$script:BackupDir\functionmap" -Recurse -Force
        Write-Ok "Function maps backed up"
    }

    Write-Ok "Pre-install backup created: $script:BackupDir"
}

function New-Directories {
    @($ToolsDir, $CommandsDir, $DocsDir, $MapsDir) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
        }
    }
    Write-Ok "Directories created"
}

# ============================================================================
#  Install files
# ============================================================================

function Install-Files {
    foreach ($f in $ToolFiles) {
        Get-InstallFile "src/tools/$f" (Join-Path $ToolsDir $f)
    }
    Write-Ok "Python tools installed (5 files)"

    foreach ($f in $CommandFiles) {
        Get-InstallFile "src/commands/$f" (Join-Path $CommandsDir $f)
    }
    Write-Ok "Skill commands installed (2 files)"

    foreach ($f in $DocFiles) {
        Get-InstallFile "src/docs/$f" (Join-Path $DocsDir $f)
    }
    Write-Ok "Help documentation installed (1 file)"
}

# ============================================================================
#  Write .version file
# ============================================================================

function Write-VersionFile {
    $pyFile = Join-Path $ToolsDir "functionmap.py"
    $version = "unknown"
    if (Test-Path $pyFile) {
        $match = Select-String -Path $pyFile -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($match) {
            $version = $match.Matches[0].Groups[1].Value
        }
    }
    $versionFile = Join-Path $ToolsDir ".version"
    [System.IO.File]::WriteAllText($versionFile, $version)
    Write-Ok "Version file written: $version"
}

# ============================================================================
#  CLAUDE.md injection
# ============================================================================

function Update-ClaudeMd {
    # Load instruction and registry content
    if ($script:SourceMode -eq "local") {
        $instrFile    = Join-Path $script:ScriptRoot "src\claude-md\functionmap-instructions.md"
        $registryFile = Join-Path $script:ScriptRoot "src\claude-md\functionmap-registry.md"
        if (-not (Test-Path $instrFile) -or -not (Test-Path $registryFile)) {
            Stop-Install "CLAUDE.md source files not found in src\claude-md\"
        }
        $instrContent    = [System.IO.File]::ReadAllText($instrFile)
        $registryContent = [System.IO.File]::ReadAllText($registryFile)
    } else {
        try {
            $instrContent    = (Invoke-WebRequest -Uri "$RepoUrl/src/claude-md/functionmap-instructions.md" -UseBasicParsing).Content
            $registryContent = (Invoke-WebRequest -Uri "$RepoUrl/src/claude-md/functionmap-registry.md" -UseBasicParsing).Content
        } catch {
            Stop-Install "Failed to download CLAUDE.md integration files"
        }
        # Ensure string type (Invoke-WebRequest may return bytes)
        if ($instrContent -is [byte[]]) {
            $instrContent = [System.Text.Encoding]::UTF8.GetString($instrContent)
        }
        if ($registryContent -is [byte[]]) {
            $registryContent = [System.Text.Encoding]::UTF8.GetString($registryContent)
        }
    }

    $InstrBegin = "<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->"
    $InstrEnd   = "<!-- FUNCTIONMAP:INSTRUCTIONS:END -->"
    $RegBegin   = "<!-- FUNCTIONMAP:BEGIN -->"
    $RegEnd     = "<!-- FUNCTIONMAP:END -->"

    # Case 1: No CLAUDE.md -- create it
    if (-not (Test-Path $ClaudeMd)) {
        $newContent = "# CLAUDE.md`n`n$instrContent`n`n$registryContent"
        [System.IO.File]::WriteAllText($ClaudeMd, $newContent)
        Write-Ok "Created $ClaudeMd with both blocks"
        return
    }

    # Create backup
    Copy-Item $ClaudeMd "$ClaudeMd.bak" -Force
    Write-Info "Backup created: CLAUDE.md.bak"

    $content = [System.IO.File]::ReadAllText($ClaudeMd)

    # Warn about potential duplication
    if ($content -match "Function Maps" -and $content -notmatch [regex]::Escape($InstrBegin)) {
        Write-Warn 'Found existing "Function Maps" section in CLAUDE.md without sentinel markers.'
        Write-Warn "The installer will append sentinel-wrapped blocks at the end of the file."
        Write-Warn "You may want to manually remove the old section to avoid duplication."
    }

    $hasInstrSentinels = $content.Contains($InstrBegin)
    $hasRegSentinels   = $content.Contains($RegBegin)

    # --- Instructions block ---
    if ($hasInstrSentinels) {
        # Extract existing instructions block for comparison
        $instrPattern = "(?s)" + [regex]::Escape($InstrBegin) + ".*?" + [regex]::Escape($InstrEnd)
        $existingInstr = [regex]::Match($content, $instrPattern).Value
        if ($existingInstr -eq $instrContent) {
            Write-Ok "Instructions block is up to date"
        } else {
            $content = [regex]::Replace($content, $instrPattern, $instrContent)
            Write-Ok "Updated instructions block in CLAUDE.md"
        }
    }

    # --- Registry block ---
    if ($hasRegSentinels) {
        # Extract existing map entries (the "- **name**..." lines) and preserve them
        $regPattern = "(?s)" + [regex]::Escape($RegBegin) + "(.*?)" + [regex]::Escape($RegEnd)
        $regMatch = [regex]::Match($content, $regPattern)
        $existingBody = $regMatch.Groups[1].Value
        $existingEntries = ($existingBody -split "`n" | Where-Object { $_ -match "^- \*\*" }) -join "`n"
        # Rebuild registry: template format + preserved entries
        if ($existingEntries) {
            $rebuiltRegistry = "$RegBegin`n### Available maps (auto-generated -- do not edit):`n$existingEntries`n`n$RegEnd"
        } else {
            $rebuiltRegistry = "$RegBegin`n### Available maps (auto-generated -- do not edit):`n`n$RegEnd"
        }
        $content = [regex]::Replace($content, $regPattern, $rebuiltRegistry)
        if ($existingEntries) {
            Write-Ok "Preserved existing map entries in registry block"
        } else {
            Write-Ok "Registry block is up to date"
        }
    }

    # --- Add missing blocks (instructions always before registry) ---
    if (-not $hasInstrSentinels) {
        if ($hasRegSentinels) {
            # Registry exists -- insert instructions BEFORE it
            $content = $content -replace [regex]::Escape($RegBegin), "$instrContent`n`n$RegBegin"
            Write-Ok "Inserted instructions block before registry in CLAUDE.md"
        } else {
            $content = $content + "`n`n" + $instrContent
            Write-Ok "Appended instructions block to CLAUDE.md"
        }
    }

    if (-not $hasRegSentinels) {
        $content = $content + "`n`n" + $registryContent
        Write-Ok "Appended registry block to CLAUDE.md"
    }

    [System.IO.File]::WriteAllText($ClaudeMd, $content)
}

# ============================================================================
#  Post-install verification
# ============================================================================

function Test-Installation {
    $errors = 0

    # Check Python can run functionmap.py --version
    try {
        $null = & $script:Python (Join-Path $ToolsDir "functionmap.py") --version 2>&1
    } catch {
        Write-Warn "functionmap.py --version failed"
        $errors++
    }

    # Verify all expected files
    $expectedFiles = @(
        (Join-Path $ToolsDir "functionmap.py"),
        (Join-Path $ToolsDir "categorize.py"),
        (Join-Path $ToolsDir "quickmap.py"),
        (Join-Path $ToolsDir "thirdparty.py"),
        (Join-Path $ToolsDir "describe.py"),
        (Join-Path $CommandsDir "functionmap.md"),
        (Join-Path $CommandsDir "functionmap-update.md"),
        (Join-Path $DocsDir "functionmap-help.md")
    )
    foreach ($f in $expectedFiles) {
        if (-not (Test-Path $f)) {
            Write-Warn "Missing: $f"
            $errors++
        }
    }

    # Verify CLAUDE.md sentinels
    if (Test-Path $ClaudeMd) {
        $mdContent = [System.IO.File]::ReadAllText($ClaudeMd)
        if ($mdContent -notmatch "FUNCTIONMAP:INSTRUCTIONS:BEGIN") {
            Write-Warn "CLAUDE.md missing instructions sentinel"
            $errors++
        }
        if ($mdContent -notmatch "FUNCTIONMAP:BEGIN") {
            Write-Warn "CLAUDE.md missing registry sentinel"
            $errors++
        }
    } else {
        Write-Warn "CLAUDE.md not found after install"
        $errors++
    }

    if ($errors -eq 0) {
        Write-Ok "All 8 files verified"
        Write-Ok "CLAUDE.md sentinels verified"
    } else {
        Write-Warn "$errors verification issue(s) found"
    }

    return $errors
}

# ============================================================================
#  Success message
# ============================================================================

function Show-Success {
    $versionFile = Join-Path $ToolsDir ".version"
    $version = if (Test-Path $versionFile) { Get-Content $versionFile -Raw } else { "unknown" }
    $version = $version.Trim()

    Write-Host ""
    Write-Host "  ============================================================"
    Write-Host "    FUNCTIONMAP v$version INSTALLED SUCCESSFULLY"
    Write-Host "  ============================================================"
    Write-Host ""
    Write-Host "    Usage (in Claude Code):"
    Write-Host "      /functionmap          Full index of a project"
    Write-Host "      /functionmap-update   Incremental update (changed files only)"
    Write-Host "      /functionmap help     Show detailed help"
    Write-Host ""
    Write-Host "    To update:  Re-run this installer"
    Write-Host "    To remove:  irm $RepoUrl/uninstall.ps1 | iex"
    Write-Host ""
    Write-Host "  ============================================================"
    Write-Host ""
}

# ============================================================================
#  Main
# ============================================================================

Show-Banner
Test-Preflight
Get-SourceMode
Confirm-Install
Backup-Existing

try {
    New-Directories
    Install-Files
    Write-VersionFile
    Update-ClaudeMd
    $null = Test-Installation
    Show-Success
    if ($script:BackupDir) {
        Write-Info "Pre-install backup: $script:BackupDir"
    }
} catch {
    Write-Host ""
    Write-Host "  [ERROR] Installation failed: $_" -ForegroundColor Red
    if ($script:BackupDir -and (Test-Path $script:BackupDir)) {
        Write-Host ""
        Write-Host "  Your original files were backed up before any changes."
        Write-Host "  To restore, run:"
        Write-Host ""
        Write-Host "    Copy-Item '$script:BackupDir\tools\*' '$ToolsDir\' -Force"
        Write-Host "    Copy-Item '$script:BackupDir\commands\*' '$CommandsDir\' -Force"
        Write-Host "    Copy-Item '$script:BackupDir\docs\*' '$DocsDir\' -Force"
        Write-Host "    Copy-Item '$script:BackupDir\CLAUDE.md' '$ClaudeMd' -Force"
        Write-Host "    Copy-Item '$script:BackupDir\functionmap\*' '$MapsDir\' -Recurse -Force"
        Write-Host ""
        Write-Host "  Backup location: $script:BackupDir"
    }
    throw
}
