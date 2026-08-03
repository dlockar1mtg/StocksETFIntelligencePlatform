$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $(git branch --show-current)"
python --version

Write-Host "`nRunning Phase 1.4 evidence quality certification..."
python .\scripts\certify_phase_1_4.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.4 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log --oneline -1

Write-Host "`nPhase 1.4 certification completed successfully."
