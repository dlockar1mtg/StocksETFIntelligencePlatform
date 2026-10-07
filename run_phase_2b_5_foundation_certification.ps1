$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $(git branch --show-current)"
python --version

Write-Host "`nRunning Phase 2B.5 market-data foundation certification..."
python -m scripts.certify_phase_2b_5_foundation

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2B.5 certification failed."
}

Write-Host "`nGit status:"
git status

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 2B.5 market-data foundation certification completed successfully."
