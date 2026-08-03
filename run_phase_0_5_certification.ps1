$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-0-completion"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 0.5 security master and ETF universe certification..."
python .\scripts\certify_phase_0_5.py
if ($LASTEXITCODE -ne 0) {
    throw "Phase 0.5 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 0.5 certification completed successfully."
