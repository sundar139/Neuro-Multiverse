#Requires -Version 5.1
<#
.SYNOPSIS
    Primary Windows validation entry point for the NeuroMultiverse repository.

.DESCRIPTION
    Runs every repository quality gate and reports a pass/fail summary.
    This script validates; it never installs packages or mutates an environment.
    Exits nonzero when any gate fails.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve the repository root from this script's location, never from a
# hardcoded user-specific path.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "FAIL: project environment interpreter not found at .venv\Scripts\python.exe"
    Write-Host "      Create it with: py -3.11 -m venv .venv"
    exit 1
}

# Keep tool caches inside the repository so they are ignored consistently.
$env:PRE_COMMIT_HOME = Join-Path $repoRoot '.cache\pre-commit'

$script:results = [ordered]@{}

# Capture the complete working-tree state, tracked and untracked, in a stable
# machine-readable format. Used to prove that validation did not modify the
# repository: auto-fixing hooks are allowed to run, but a run that changes files
# and still reports success would be reporting a result it just manufactured.
# Returns a single newline-joined string, never an array: a PowerShell function
# returning an empty array unrolls to $null on assignment, which would make a
# clean tree indistinguishable from a failed capture. A clean tree returns ''.
# Only a genuine capture failure returns $null.
function Get-PorcelainState {
    if (-not $script:gitAvailable) { return $null }
    $state = & git status --porcelain=v1 --untracked-files=all 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    if ($null -eq $state) { return '' }
    return (@($state) -join "`n")
}

$script:gitAvailable = $false
& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -eq 0) { $script:gitAvailable = $true }

$script:initialState = Get-PorcelainState

function Invoke-Gate {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host ''
    Write-Host "--- $Name ---"
    try {
        $global:LASTEXITCODE = 0
        & $Action
        if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
            throw "exit code $LASTEXITCODE"
        }
        $script:results[$Name] = 'PASS'
    }
    catch {
        Write-Host "  $($_.Exception.Message)"
        $script:results[$Name] = 'FAIL'
    }
}

Write-Host '=== NeuroMultiverse repository verification ==='
Write-Host "Repository root: $repoRoot"

# Provenance: which commit is being validated.
$commit = (& git rev-parse HEAD 2>$null)
if ($LASTEXITCODE -eq 0) {
    $dirty = (& git status --porcelain)
    $state = if ([string]::IsNullOrWhiteSpace($dirty)) { 'clean' } else { 'dirty' }
    Write-Host "Commit: $commit ($state)"
}
else {
    Write-Host 'Commit: unavailable (git not found or not a repository)'
}

Invoke-Gate 'Python version' {
    $version = & $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    Write-Host "  Interpreter reports: $version"
    if (-not $version.StartsWith('3.11.')) {
        throw "expected Python 3.11.x, found $version"
    }
}

Invoke-Gate 'Ruff format' { & $python -m ruff format --check . }
Invoke-Gate 'Ruff lint' { & $python -m ruff check . }
Invoke-Gate 'Mypy' { & $python -m mypy src tests }
Invoke-Gate 'Pytest' { & $python -m pytest -ra --strict-markers }

Invoke-Gate 'Runtime metadata' {
    $json = & $python -m neuromultiverse.runtime --json
    if ($LASTEXITCODE -ne 0) { throw "runtime module exited $LASTEXITCODE" }
    $null = $json | ConvertFrom-Json
    Write-Host '  Runtime metadata emitted parsable JSON.'
}

Invoke-Gate 'Pre-commit' { & $python -m pre_commit run --all-files }

Invoke-Gate 'Oversized files' {
    $ignored = '\\\.git\\|\\\.venv\\|\\renv\\|\\\.cache\\|\\__pycache__\\|\\\.mypy_cache\\|\\\.ruff_cache\\|\\\.pytest_cache\\'
    $large = Get-ChildItem -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch $ignored -and $_.Length -gt 5MB }
    if ($large) {
        $large | ForEach-Object { Write-Host "  $($_.FullName) ($([math]::Round($_.Length / 1MB, 1)) MB)" }
        throw "$($large.Count) file(s) exceed 5 MB outside ignored directories"
    }
    Write-Host '  No file over 5 MB outside ignored directories.'
}

Invoke-Gate 'Tracked data and model artifacts' {
    $tracked = & git ls-files
    $offenders = $tracked | Where-Object {
        $_ -match '\.(nii|nii\.gz|h5|hdf5|npy|npz|pt|pth|ckpt|safetensors)$' -or
        $_ -match '(^|/)(data/raw|data/derivatives|data/interim|data/features|work|scratch|results|artifacts)/'
    }
    if ($offenders) {
        $offenders | ForEach-Object { Write-Host "  $_" }
        throw "$($offenders.Count) prohibited artifact path(s) tracked"
    }
    Write-Host '  No imaging data, derivative, or model weight is tracked.'
}

Invoke-Gate 'Credential scan' {
    $patterns = @(
        'AKIA[0-9A-Z]{16}',
        '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
        'ghp_[A-Za-z0-9]{20,}',
        'sk-[A-Za-z0-9_-]{20,}',
        '(?i)(password|api[_-]?key|secret|token)\s*[:=]\s*["''][^"'']{6,}["'']'
    )
    $found = @()
    foreach ($file in (& git ls-files)) {
        if (Test-Path -LiteralPath $file -PathType Leaf) {
            foreach ($pattern in $patterns) {
                $hit = Select-String -LiteralPath $file -Pattern $pattern -ErrorAction SilentlyContinue
                if ($hit) { $found += $hit }
            }
        }
    }
    if ($found) {
        $found | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber)" }
        throw "$($found.Count) potential credential match(es)"
    }
    Write-Host '  No credential pattern found in tracked files.'
}

Invoke-Gate 'Git diff check' {
    if (-not $script:gitAvailable) { throw 'git not available' }
    & git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'git diff --check (working tree) reported problems' }
    & git diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check (staged) reported problems' }
    Write-Host '  No whitespace errors or conflict markers in the working-tree or staged diff.'
}

# Must remain the last gate: it compares against the state captured at startup,
# so every preceding gate has had its chance to modify the tree.
Invoke-Gate 'Working-tree stability' {
    if (-not $script:gitAvailable) { throw 'git not available' }
    $before = $script:initialState
    $after = Get-PorcelainState
    if ($null -eq $before -or $null -eq $after) {
        throw 'could not capture working-tree state'
    }
    if ($before -ne $after) {
        Write-Host '  Validation MODIFIED the working tree. State before:'
        if ($before -eq '') { Write-Host '    (clean)' }
        else { $before -split "`n" | ForEach-Object { Write-Host "    $_" } }
        Write-Host '  State after:'
        if ($after -eq '') { Write-Host '    (clean)' }
        else { $after -split "`n" | ForEach-Object { Write-Host "    $_" } }
        Write-Host '  Nothing was reverted automatically. Review and stage or discard as intended.'
        throw 'working tree changed during validation'
    }
    # A dirty starting tree is fine; an unchanged dirty tree still passes.
    if ($before -eq '') {
        Write-Host '  Working tree unchanged by validation (started clean).'
    }
    else {
        $count = ($before -split "`n").Count
        Write-Host "  Working tree unchanged by validation (started dirty, $count entr(y/ies))."
    }
}

Write-Host ''
Write-Host '=== Summary ==='
$failed = 0
foreach ($entry in $script:results.GetEnumerator()) {
    Write-Host ("{0,-34} {1}" -f $entry.Key, $entry.Value)
    if ($entry.Value -eq 'FAIL') { $failed++ }
}
Write-Host ''
if ($failed -gt 0) {
    Write-Host "RESULT: FAIL ($failed of $($script:results.Count) gates failed)"
    exit 1
}
Write-Host "RESULT: PASS (all $($script:results.Count) gates passed)"
exit 0
