$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$ExpectedBranch = "phase-1-data-foundation"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $RepoRoot"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 1.1 provider contract certification..."
python .\scripts\certify_phase_1_1.py
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.1 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline

Write-Host "`nPhase 1.1 certification completed successfully."
