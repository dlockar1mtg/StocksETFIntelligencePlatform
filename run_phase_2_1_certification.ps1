$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-2.1-analytics-contracts"
$CurrentBranch = (git branch --show-current).Trim()

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 2.1 analytics architecture and metric contract certification..."
python -m scripts.certify_phase_2_1

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2.1 certification failed."
}

Write-Host "`nGit status:"
git status

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 2.1 certification completed successfully."
