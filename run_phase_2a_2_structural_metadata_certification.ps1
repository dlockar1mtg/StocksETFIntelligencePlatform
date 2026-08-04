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

Write-Host "`nRunning Phase 2A.2 structural metadata certification..."
python .\scripts\certify_phase_2a_2_structural_metadata.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2A.2 structural metadata certification failed."
}

Write-Host "`nGit status:"
git status

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 2A.2 structural metadata certification completed successfully."
