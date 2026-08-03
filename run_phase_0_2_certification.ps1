$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-0.2-repository-foundation"
$CurrentBranch = (git branch --show-current).Trim()

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

python --version
if ($LASTEXITCODE -ne 0) {
    throw "Python is unavailable."
}

python .\scripts\certify_phase_0_2.py
if ($LASTEXITCODE -ne 0) {
    throw "Phase 0.2 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short
Write-Host "`nLatest commit:"
git log -1 --oneline
Write-Host "`nPhase 0.2 certification completed successfully."
