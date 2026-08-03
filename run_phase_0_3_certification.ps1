$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-0.3-contracts-configuration"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 0.3 contract and configuration certification..."
python .\scripts\certify_phase_0_3.py
if ($LASTEXITCODE -ne 0) {
    throw "Phase 0.3 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short
Write-Host "`nLatest commit:"
git log -1 --oneline
Write-Host "`nPhase 0.3 certification completed successfully."
