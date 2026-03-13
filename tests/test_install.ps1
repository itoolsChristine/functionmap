$ErrorActionPreference = 'Stop'

$Pass = 0
$Fail = 0
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir

function Test-Pass($Message) {
    $script:Pass++
    Write-Host "  PASS: $Message"
}

function Test-Fail($Message) {
    $script:Fail++
    Write-Host "  FAIL: $Message" -ForegroundColor Red
}

function Test-FileExists($Path, $Description) {
    if (Test-Path $Path) {
        Test-Pass $Description
    } else {
        Test-Fail "$Description -- file not found: $Path"
    }
}

function Test-Sentinel($FilePath, $Marker, $Description) {
    if ((Test-Path $FilePath) -and (Select-String -Path $FilePath -Pattern $Marker -Quiet)) {
        Test-Pass $Description
    } else {
        Test-Fail "$Description -- sentinel not found in $FilePath"
    }
}

# -------------------------------------------------------------------
# Setup: create a fake USERPROFILE with .claude/ directory
# -------------------------------------------------------------------
$FakeHome = Join-Path ([System.IO.Path]::GetTempPath()) ("functionmap_test_" + [System.Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $FakeHome -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $FakeHome '.claude') -Force | Out-Null

$OriginalUserProfile      = $env:USERPROFILE
$env:USERPROFILE          = $FakeHome

Write-Host ""
Write-Host "=========================================="
Write-Host "  Functionmap Install Tests (PowerShell)"
Write-Host "=========================================="
Write-Host "  Fake USERPROFILE: $FakeHome"
Write-Host ""

try {
    # -------------------------------------------------------------------
    # Run installer
    # -------------------------------------------------------------------
    Write-Host "--- First install ---"
    try {
        & "$RepoRoot\install.ps1"
        Test-Pass "install.ps1 exited successfully"
    } catch {
        Test-Fail "install.ps1 exited with error: $_"
    }

    # -------------------------------------------------------------------
    # Verify files exist
    # -------------------------------------------------------------------
    Write-Host ""
    Write-Host "--- File checks ---"
    $Base = Join-Path $FakeHome '.claude'

    Test-FileExists (Join-Path $Base 'commands\functionmap.md')          'commands/functionmap.md'
    Test-FileExists (Join-Path $Base 'commands\functionmap-update.md')   'commands/functionmap-update.md'
    Test-FileExists (Join-Path $Base 'docs\functionmap-help.md')         'docs/functionmap-help.md'
    Test-FileExists (Join-Path $Base 'tools\functionmap\functionmap.py') 'tools/functionmap.py'
    Test-FileExists (Join-Path $Base 'tools\functionmap\categorize.py')  'tools/categorize.py'
    Test-FileExists (Join-Path $Base 'tools\functionmap\quickmap.py')    'tools/quickmap.py'
    Test-FileExists (Join-Path $Base 'tools\functionmap\thirdparty.py')  'tools/thirdparty.py'
    Test-FileExists (Join-Path $Base 'tools\functionmap\describe.py')    'tools/describe.py'

    # -------------------------------------------------------------------
    # Verify CLAUDE.md sentinels
    # -------------------------------------------------------------------
    Write-Host ""
    Write-Host "--- Sentinel checks ---"
    $ClaudeMd = Join-Path $Base 'CLAUDE.md'

    Test-FileExists $ClaudeMd 'CLAUDE.md exists'
    Test-Sentinel $ClaudeMd 'FUNCTIONMAP:INSTRUCTIONS:BEGIN' 'Instructions BEGIN sentinel'
    Test-Sentinel $ClaudeMd 'FUNCTIONMAP:INSTRUCTIONS:END'   'Instructions END sentinel'
    Test-Sentinel $ClaudeMd 'FUNCTIONMAP:BEGIN'               'Registry BEGIN sentinel'
    Test-Sentinel $ClaudeMd 'FUNCTIONMAP:END'                 'Registry END sentinel'

    # -------------------------------------------------------------------
    # Verify .version file
    # -------------------------------------------------------------------
    Write-Host ""
    Write-Host "--- Version check ---"
    Test-FileExists (Join-Path $Base 'tools\functionmap\.version') '.version file'

    # -------------------------------------------------------------------
    # Idempotency: run installer again
    # -------------------------------------------------------------------
    Write-Host ""
    Write-Host "--- Idempotency (second install) ---"
    try {
        & "$RepoRoot\install.ps1"
        Test-Pass "install.ps1 idempotent re-run succeeded"
    } catch {
        Test-Fail "install.ps1 idempotent re-run failed: $_"
    }

} finally {
    # -------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------
    $env:USERPROFILE = $OriginalUserProfile
    Remove-Item -Recurse -Force $FakeHome -ErrorAction SilentlyContinue
}

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
Write-Host ""
Write-Host "=========================================="
$Total = $Pass + $Fail
Write-Host "  Results: $Pass/$Total passed"
if ($Fail -gt 0) {
    Write-Host "  $Fail FAILED" -ForegroundColor Red
    Write-Host "=========================================="
    exit 1
}
Write-Host "  All tests passed."
Write-Host "=========================================="
exit 0
