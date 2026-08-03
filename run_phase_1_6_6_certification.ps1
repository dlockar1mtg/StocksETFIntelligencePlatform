$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "Repository: $RepoRoot"
Write-Host "Branch: $((git branch --show-current).Trim())"
python --version

Write-Host "`nRunning Phase 1.6.6 dated Robinhood universe snapshot certification..."
python .\scripts\certify_phase_1_6_6.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.6.6 certification failed."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline --decorate

Write-Host "`nPhase 1.6.6 certification completed successfully."
