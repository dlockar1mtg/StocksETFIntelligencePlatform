$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedBranch = "phase-0.1-governance-authority"
$CurrentBranch = (git branch --show-current).Trim()

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $(Get-Location)"
Write-Host "Branch: $CurrentBranch"
Write-Host "Python:"
python --version

Write-Host "`nRunning Phase 0.1 governance and ETF regression tests..."
python scripts\certify_phase_0_1.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 0.1 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline

Write-Host "`nPhase 0.1 certification completed successfully."
