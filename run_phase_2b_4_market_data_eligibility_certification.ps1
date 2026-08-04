$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedBranch = "phase-2b-market-data-foundation"
$CurrentBranch = (git branch --show-current).Trim()

Write-Host "Repository: $(Get-Location)"
Write-Host "Branch: $CurrentBranch"
python --version

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

if (git status --porcelain) {
    throw "The working tree is not clean."
}

Write-Host "`nRunning Phase 2B.4 market-data eligibility certification..."
python -m scripts.certify_phase_2b_4_market_data_eligibility

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2B.4 certification failed."
}

Write-Host "`nGit status:"
git status
Write-Host "`nLatest commit:"
git log -1 --oneline --decorate
Write-Host "`nPhase 2B.4 market-data eligibility certification completed successfully."
