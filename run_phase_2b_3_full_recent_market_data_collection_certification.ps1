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
    throw "Working tree is not clean."
}

Write-Host "`nRunning Phase 2B.3 certification..."
python -m scripts.certify_phase_2b_3_full_recent_market_data_collection

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2B.3 certification failed."
}

Write-Host "`nGit status:"
git status
Write-Host "`nLatest commit:"
git log -1 --oneline --decorate
Write-Host "`nPhase 2B.3 certification completed successfully."
