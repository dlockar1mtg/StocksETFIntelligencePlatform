$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-2-etf-structural-triage"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Expected branch '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 2A.3 SEC acquisition certification..."
python -m scripts.certify_phase_2a_3_sec_acquisition
if ($LASTEXITCODE -ne 0) {
    throw "Phase 2A.3 SEC acquisition certification failed."
}

Write-Host "`nGit status:"
git status
Write-Host "`nLatest commit:"
git log -1 --oneline
Write-Host "`nPhase 2A.3 SEC acquisition certification completed successfully."
