$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Repository: $Root"
Write-Host "Branch: $((git branch --show-current).Trim())"
python --version

Write-Host "`nRunning Phase 1.6.5 analytics eligibility certification..."
python .\scripts\certify_phase_1_6_5.py

if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.6.5 certification failed."
}

Write-Host "`nGit status:"
git status --short

Write-Host "`nLatest commit:"
git log -1 --oneline

Write-Host "`nPhase 1.6.5 certification completed successfully."
