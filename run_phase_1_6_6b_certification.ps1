$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedBranch = "phase-1.6-robinhood-etf-universe"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $((Get-Location).Path)"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 1.6.6b Robinhood availability collector certification..."
python -m scripts.certify_phase_1_6_6b
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.6.6b certification failed."
}

Write-Host "`nGit status:"
git status --short
Write-Host "`nLatest commit:"
git log -1 --oneline --decorate
Write-Host "`nPhase 1.6.6b certification completed successfully."
