$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "Repository: $RepoRoot"
Write-Host "Branch: $(git branch --show-current)"
python --version

Write-Host "`nRunning Phase 1.3 normalization certification..."
python .\scripts\certify_phase_1_3.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.3 certification failed with exit code $LASTEXITCODE."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline

Write-Host "`nPhase 1.3 certification completed successfully."
