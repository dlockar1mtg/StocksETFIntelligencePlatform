$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ExpectedBranch = "phase-1.6-robinhood-etf-universe"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $Root"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 1.6.1 dynamic ETF universe certification..."
python .\scripts\certify_phase_1_6_1.py
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.6.1 certification failed."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline

Write-Host "`nPhase 1.6.1 certification completed successfully."
