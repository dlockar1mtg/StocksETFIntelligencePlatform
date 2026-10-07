$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $((git branch --show-current).Trim())"
python --version

$ExpectedBranch = "phase-2b-market-data-foundation"
$CurrentBranch = (git branch --show-current).Trim()

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "`nRunning Phase 2B.1 market-data screen certification..."
python .\scripts\certify_phase_2b_1_market_data_screen.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2B.1 market-data screen certification failed."
}

Write-Host "`nGit status:"
git status

Write-Host "`nLatest commit:"
git log -1 --oneline

Write-Host "`nPhase 2B.1 market-data screen certification completed successfully."
