$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedBranch = "phase-2b-market-data-foundation"
$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$CurrentBranch = (git branch --show-current).Trim()
Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"
python --version

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "`nRunning Phase 2B.2 recent market-data certification..."
python -m scripts.certify_phase_2b_2_recent_market_data
if ($LASTEXITCODE -ne 0) {
    throw "Phase 2B.2 certification failed."
}

Write-Host "`nGit status:"
git status
Write-Host "`nLatest commit:"
git log -1 --oneline
Write-Host "`nPhase 2B.2 recent market-data certification completed successfully."
