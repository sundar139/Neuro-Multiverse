#Requires -Version 5.1
<#
.SYNOPSIS
    System-readiness verification for the NeuroMultiverse toolchain on Windows.

.DESCRIPTION
    Verifies the already-installed cross-platform environment: the Windows
    Python and PyTorch stack, both GPU views, Docker on Windows and inside
    Ubuntu 24.04, Windows R and the project renv lock, the neuroimaging tools
    inside WSL2 (by invoking the committed Bash verifier), and the pinned
    container identities.

    This script VERIFIES; it never installs, upgrades, repairs, or reconfigures
    software, and it never runs a research workload. It reads only versions,
    metadata, and digests. It resolves every host-specific location at runtime
    and records no username or user-specific absolute path.

    Exits nonzero when any gate fails.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\verify_system.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Expected measurements on the approved reference machine -----------------
$Expect = @{
    FmriprepTag       = 'nipreps/fmriprep:25.2.5'
    FmriprepVersion   = '25.2.5'
    FmriprepDigest    = 'nipreps/fmriprep@sha256:15cbf8dcd17440d26ff5e80e9f7313f1cb3c54f13673f1ec4aed4465e8e12d77'
    FmriprepId        = 'sha256:15cbf8dcd17440d26ff5e80e9f7313f1cb3c54f13673f1ec4aed4465e8e12d77'
    AromaTag          = 'nipreps/fmripost-aroma:0.0.12'
    AromaVersion      = '0.0.12'
    AromaDigest       = 'nipreps/fmripost-aroma@sha256:06388c67ebb8a07b7f9a4ec065e7bcaf7ece0e03cdceee20b4d42a657c338668'
    AromaId           = 'sha256:06388c67ebb8a07b7f9a4ec065e7bcaf7ece0e03cdceee20b4d42a657c338668'
    Distro            = 'Ubuntu-24.04'
}

# --- Repository root, resolved from this script's own location ---------------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'

# --- Git working-tree state, captured before any check runs ------------------
$script:gitAvailable = $false
& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -eq 0) { $script:gitAvailable = $true }

function Get-PorcelainState {
    if (-not $script:gitAvailable) { return $null }
    $state = & git status --porcelain=v1 --untracked-files=all 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    if ($null -eq $state) { return '' }
    return (@($state) -join "`n")
}

$script:initialState = Get-PorcelainState

# --- Convert the repository path to a WSL path with wslpath ------------------
# wslpath is the authoritative converter; a manual backslash-to-slash rewrite
# would mishandle drive letters and spaces. Guard against an empty result so a
# failed conversion never degrades into an interactive `wsl` shell.
function ConvertTo-WslPath {
    param([Parameter(Mandatory = $true)][string]$WindowsPath)
    $converted = & wsl -d $Expect.Distro -- wslpath -a "$WindowsPath" 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($converted)) {
        throw "could not convert path to WSL form: $WindowsPath"
    }
    return $converted.Trim()
}

# --- Gate bookkeeping --------------------------------------------------------
$script:results = [ordered]@{}

function Invoke-Gate {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host ''
    Write-Host "--- $Name ---"
    try {
        & $Action
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            throw "exit code $LASTEXITCODE"
        }
        $script:results[$Name] = 'PASS'
    }
    catch {
        Write-Host "  $($_.Exception.Message)"
        $script:results[$Name] = 'FAIL'
    }
}

# --- Helpers for container inspection ----------------------------------------
function Get-ImageField {
    param([string]$Ref, [string]$Format)
    $value = & docker image inspect $Ref --format $Format 2>$null
    if ($LASTEXITCODE -ne 0) { throw "docker image inspect failed for $Ref" }
    return ($value | Out-String).Trim()
}

function Get-ImageRepoDigest {
    param([string]$Ref)
    $digests = & docker image inspect $Ref --format '{{range .RepoDigests}}{{println .}}{{end}}' 2>$null
    if ($LASTEXITCODE -ne 0) { throw "docker image inspect failed for $Ref" }
    return @($digests | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() })
}

function Read-VersionField {
    param([string]$File, [string]$Label)
    $line = Select-String -LiteralPath $File -Pattern ("^{0}:\s*(.+)$" -f [regex]::Escape($Label)) |
        Select-Object -First 1
    if (-not $line) { throw "field '$Label' not found in $File" }
    return $line.Matches[0].Groups[1].Value.Trim()
}

function Assert-Image {
    param(
        [string]$Ref, [string]$ExpectVersion, [string]$ExpectDigest,
        [string]$ExpectId, [string]$VersionFile
    )
    $id = Get-ImageField -Ref $Ref -Format '{{.Id}}'
    $arch = Get-ImageField -Ref $Ref -Format '{{.Architecture}}'
    $os = Get-ImageField -Ref $Ref -Format '{{.Os}}'
    $digests = Get-ImageRepoDigest -Ref $Ref
    $appVersion = ((& docker run --rm $Ref --version 2>$null) | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "docker run --version failed for $Ref" }

    Write-Host "  reference:    $Ref"
    Write-Host "  app version:  $appVersion"
    Write-Host "  image ID:     $id"
    Write-Host "  architecture: $arch"
    Write-Host "  os:           $os"

    if ($arch -ne 'amd64') { throw "architecture is $arch, expected amd64" }
    if ($os -ne 'linux') { throw "os is $os, expected linux" }
    if ($id -ne $ExpectId) { throw "image ID mismatch: live $id vs expected $ExpectId" }
    if ($appVersion -notlike "*$ExpectVersion*") { throw "app version mismatch: '$appVersion' lacks $ExpectVersion" }
    if ($digests -notcontains $ExpectDigest) { throw "immutable digest not present on image: $ExpectDigest" }

    # Committed lock file must match the live image exactly.
    $fileVersion = Read-VersionField -File $VersionFile -Label 'Application version'
    $fileDigest = Read-VersionField -File $VersionFile -Label 'Immutable digest'
    $fileId = Read-VersionField -File $VersionFile -Label 'Image ID'
    $fileArch = Read-VersionField -File $VersionFile -Label 'Architecture'
    $fileOs = Read-VersionField -File $VersionFile -Label 'Operating system'
    if ($fileVersion -ne $ExpectVersion) { throw "$VersionFile version $fileVersion != $ExpectVersion" }
    if ($fileDigest -ne $ExpectDigest) { throw "$VersionFile digest mismatch" }
    if ($fileId -ne $ExpectId) { throw "$VersionFile image ID mismatch" }
    if ($fileArch -ne 'amd64') { throw "$VersionFile architecture $fileArch != amd64" }
    if ($fileOs -ne 'linux') { throw "$VersionFile os $fileOs != linux" }
    Write-Host "  committed lock file matches live image."
}

# --- Header ------------------------------------------------------------------
Write-Host '=== NeuroMultiverse system verification ==='
Write-Host "Repository root: $repoRoot"
$commit = (& git rev-parse HEAD 2>$null)
if ($LASTEXITCODE -eq 0) {
    $dirty = (& git status --porcelain)
    $state = if ([string]::IsNullOrWhiteSpace($dirty)) { 'clean' } else { 'dirty' }
    Write-Host "Commit: $commit ($state)"
}

# --- Gates -------------------------------------------------------------------
Invoke-Gate 'Project Python 3.11' {
    if (-not (Test-Path $python)) { throw "interpreter not found at .venv\Scripts\python.exe" }
    $version = & $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    Write-Host "  interpreter reports: $version"
    if (-not $version.StartsWith('3.11.')) { throw "expected Python 3.11.x, found $version" }
}

Invoke-Gate 'pip check' { & $python -m pip check }

Invoke-Gate 'PyTorch and CUDA' {
    # The probe is written to a temp file rather than passed with -c: Windows
    # PowerShell strips embedded double quotes when handing an argument to a
    # native process, which would corrupt the inline Python source.
    $src = @'
import json, torch
print(json.dumps({
    'torch': torch.__version__,
    'cuda_build': torch.version.cuda,
    'available': bool(torch.cuda.is_available()),
    'devices': torch.cuda.device_count(),
}))
'@
    $tmp = Join-Path $env:TEMP ('nm_torch_' + [guid]::NewGuid().ToString('N') + '.py')
    [System.IO.File]::WriteAllText($tmp, $src, [System.Text.Encoding]::ASCII)
    try {
        $out = & $python $tmp
        if ($LASTEXITCODE -ne 0) { throw "torch probe failed" }
    }
    finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    Write-Host "  $out"
    $info = $out | ConvertFrom-Json
    if (-not $info.available) { throw "CUDA not available to PyTorch" }
    if ($info.devices -lt 1) { throw "no CUDA device visible" }
}

Invoke-Gate 'Windows GPU' {
    $gpu = & nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
    if ($LASTEXITCODE -ne 0) { throw "nvidia-smi failed on Windows" }
    Write-Host "  $gpu"
}

Invoke-Gate 'WSL GPU' {
    $gpu = & wsl -d $Expect.Distro -- nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
    if ($LASTEXITCODE -ne 0) { throw "nvidia-smi failed inside $($Expect.Distro)" }
    Write-Host "  $gpu"
}

Invoke-Gate 'Windows Docker' {
    $ver = & docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
    if ($LASTEXITCODE -ne 0) { throw "docker daemon unreachable on Windows" }
    Write-Host "  $ver"
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "docker info failed on Windows" }
}

Invoke-Gate 'Docker from WSL' {
    $ver = & wsl -d $Expect.Distro -- docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
    if ($LASTEXITCODE -ne 0) { throw "docker unreachable inside $($Expect.Distro)" }
    Write-Host "  $ver"
}

Invoke-Gate 'Windows R 4.6.1 (64-bit)' {
    $ver = (& Rscript -e "cat(R.version.string)" 2>$null)
    if ($LASTEXITCODE -ne 0) { throw "Rscript not available on PATH" }
    $bits = (& Rscript -e "cat(.Machine`$sizeof.pointer * 8L)" 2>$null)
    Write-Host "  $ver ($bits-bit)"
    if ($ver -notlike '*4.6.1*') { throw "expected R 4.6.1, found: $ver" }
    if ($bits.Trim() -ne '64') { throw "expected 64-bit R, found $bits-bit" }
}

Invoke-Gate 'renv lock synchronized' {
    # Written to a temp file for the same quoting reason as the PyTorch probe.
    # renv::load activates the project so its library (which carries the
    # jsonvalidate/V8 schema-validation dependencies) is on the path even when R
    # is started without loading the project .Rprofile. lockfile_validate is
    # called with NAMED project/lockfile arguments: the positional single-string
    # form passes the lockfile as the project and does not validate the schema.
    $src = @'
suppressPackageStartupMessages(library(renv))
invisible(renv::load("."))
lock <- renv::lockfile_read("renv.lock")
stopifnot(!is.null(lock$Packages$renv))
stopifnot(lock$R$Version == as.character(getRversion()))
cat("R", lock$R$Version, "renv", lock$Packages$renv$Version, "\n")
renv::status(project = ".")
result <- renv::lockfile_validate(project = ".", lockfile = "renv.lock", error = TRUE, verbose = TRUE)
stopifnot(isTRUE(result))
cat("RENV_SCHEMA_VALID\n")
'@
    $tmp = Join-Path $env:TEMP ('nm_renv_' + [guid]::NewGuid().ToString('N') + '.R')
    [System.IO.File]::WriteAllText($tmp, $src, [System.Text.Encoding]::ASCII)
    # R writes package and progress messages to stderr. Under
    # $ErrorActionPreference = 'Stop', merging stderr with 2>&1 makes PowerShell
    # wrap each stderr line as a terminating error. Relax to 'Continue' for the
    # capture only; Rscript's exit code, not stderr presence, decides success.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = (& Rscript $tmp 2>&1 | Out-String)
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevEAP
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
    if ($code -ne 0) { throw "renv lock unreadable, out of sync, or schema validation failed" }
    if ($out -notmatch 'consistent|No issues') { throw "renv::status did not report a consistent project" }
    if ($out -notmatch 'RENV_SCHEMA_VALID') { throw "renv::lockfile_validate did not return TRUE" }
    Write-Host "  $(($out -split "`n" | Where-Object { $_ -match '^R\s' } | Select-Object -First 1))"
    Write-Host "  renv::status reports a consistent project; schema validation returned TRUE."
}

Invoke-Gate 'Neuroimaging tools (WSL)' {
    $wslScript = ConvertTo-WslPath -WindowsPath (Join-Path $repoRoot 'scripts\verify_neuroimaging.sh')
    if ([string]::IsNullOrWhiteSpace($wslScript)) { throw "computed WSL script path is empty" }
    & wsl -d $Expect.Distro -- bash "$wslScript"
    if ($LASTEXITCODE -ne 0) { throw "neuroimaging verification failed inside $($Expect.Distro)" }
}

Invoke-Gate 'Container: fMRIPrep' {
    Assert-Image -Ref $Expect.FmriprepTag -ExpectVersion $Expect.FmriprepVersion `
        -ExpectDigest $Expect.FmriprepDigest -ExpectId $Expect.FmriprepId `
        -VersionFile (Join-Path $repoRoot 'containers\fmriprep.version')
}

Invoke-Gate 'Container: fMRIPost-AROMA' {
    Assert-Image -Ref $Expect.AromaTag -ExpectVersion $Expect.AromaVersion `
        -ExpectDigest $Expect.AromaDigest -ExpectId $Expect.AromaId `
        -VersionFile (Join-Path $repoRoot 'containers\fmripost_aroma.version')
}

Invoke-Gate 'Container checksums file' {
    $checksums = Get-Content (Join-Path $repoRoot 'containers\checksums.txt')
    if ($checksums -notcontains $Expect.FmriprepDigest) { throw "fMRIPrep digest missing from checksums.txt" }
    if ($checksums -notcontains $Expect.AromaDigest) { throw "fMRIPost-AROMA digest missing from checksums.txt" }
    Write-Host "  both immutable digests recorded in checksums.txt"
}

Invoke-Gate 'FreeSurfer license (WSL)' {
    # Metadata only; the license contents are never read through this path.
    # No embedded double quotes: PowerShell strips them before wsl sees them.
    # The license path contains no spaces, so bare $HOME expansion is safe.
    $meta = & wsl -d $Expect.Distro -- bash -lc 'test -f $HOME/licenses/license.txt && stat -c %a $HOME/licenses/license.txt'
    if ($LASTEXITCODE -ne 0) { throw "FreeSurfer license not found inside $($Expect.Distro)" }
    Write-Host "  FreeSurfer license present, mode $($meta.Trim())"
    if ($meta.Trim() -ne '600') { throw "license mode is $($meta.Trim()), expected 600" }
}

Invoke-Gate 'Git diff check' {
    if (-not $script:gitAvailable) { throw 'git not available' }
    & git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check (working tree) reported problems' }
    & git diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check (staged) reported problems' }
    Write-Host '  no whitespace errors or conflict markers in the working-tree or staged diff.'
}

# Must remain the last gate.
Invoke-Gate 'Working-tree stability' {
    if (-not $script:gitAvailable) { throw 'git not available' }
    $after = Get-PorcelainState
    if ($null -eq $script:initialState -or $null -eq $after) { throw 'could not capture working-tree state' }
    if ($script:initialState -ne $after) { throw 'verification changed the working tree' }
    Write-Host '  working tree unchanged by verification.'
}

# --- Summary -----------------------------------------------------------------
Write-Host ''
Write-Host '=== Summary ==='
$failed = 0
foreach ($entry in $script:results.GetEnumerator()) {
    Write-Host ("{0,-32} {1}" -f $entry.Key, $entry.Value)
    if ($entry.Value -eq 'FAIL') { $failed++ }
}
Write-Host ''
if ($failed -gt 0) {
    Write-Host "RESULT: FAIL ($failed of $($script:results.Count) gates failed)"
    exit 1
}
Write-Host "RESULT: PASS (all $($script:results.Count) gates passed)"
exit 0
