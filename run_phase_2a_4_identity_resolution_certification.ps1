$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ExpectedBranch = "phase-2-etf-structural-triage"
$CurrentBranch = (git branch --show-current).Trim()

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

Write-Host "Repository: $Root"
Write-Host "Branch: $CurrentBranch"
python --version

Write-Host "`nRunning Phase 2A.4 structural identity resolution certification..."
python -m scripts.certify_phase_2a_4_identity_resolution

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2A.4 certification failed."
}

Write-Host "`nGit status:"
git status

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 2A.4 identity resolution certification completed successfully."
