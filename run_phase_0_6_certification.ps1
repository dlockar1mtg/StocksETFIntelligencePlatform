$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-0-completion"
$CurrentBranch = (git branch --show-current).Trim()

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Phase 0.6 certification must run on '$ExpectedBranch'. Current branch: '$CurrentBranch'."
}

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 0.6 calendar, return, and corporate-action certification..."
python .\scripts\certify_phase_0_6.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 0.6 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log --oneline -1

Write-Host "`nPhase 0.6 certification completed successfully."
