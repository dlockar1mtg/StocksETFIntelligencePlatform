$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-2-etf-structural-triage"
$CurrentBranch = (git branch --show-current).Trim()

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"
python --version

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "`nRunning Phase 2A structural triage certification..."
python .\scripts\certify_phase_2a_structural_triage.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2A structural triage certification failed."
}

Write-Host "`nGit status:"
git status

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 2A structural triage certification completed successfully."
