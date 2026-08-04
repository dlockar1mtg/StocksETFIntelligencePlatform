$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $(git branch --show-current)"
python --version

Write-Host "`nRunning Phase 2A.5 active structural universe certification..."
python .\scripts\certify_phase_2a_5_active_universe.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 2A.5 active universe certification failed."
}

Write-Host "`nGit status:"
git status

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 2A.5 active universe certification completed successfully."
