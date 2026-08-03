$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

Write-Host "Repository: $RepositoryRoot"
Write-Host "Branch: $(git branch --show-current)"
python --version

Write-Host "`nRunning integrated Phase 1 certification..."
python .\scripts\certify_phase_1_5.py

if ($LASTEXITCODE -ne 0) {
    throw "Integrated Phase 1 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nIntegrated Phase 1 certification completed successfully."
