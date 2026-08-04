$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedBranch = "phase-1.6-robinhood-etf-universe"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

$SnapshotPath = ".\data\certified\2026-08-03\robinhood_full_universe_snapshot.json"
if (-not (Test-Path $SnapshotPath)) {
    throw "Certified Phase 1.6.6c snapshot is missing: $SnapshotPath"
}

$ExpectedHash = "28d3f083521cb2bbbdd8fe6acf92c5c99eadd52a1180505e8b4ca7c0cadf0e32"
$ActualHash = (Get-FileHash -Path $SnapshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedHash) {
    throw "Certified snapshot hash drift detected. Expected $ExpectedHash but found $ActualHash."
}

Write-Host "Repository: $((Get-Location).Path)"
Write-Host "Branch: $CurrentBranch"
python --version
Write-Host "Snapshot SHA256: $ActualHash"
Write-Host "`nRunning Phase 1.6.7 integrated Phase 1 recertification..."

python -m scripts.certify_phase_1_6_7
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.6.7 certification failed."
}

Write-Host "`nGit status:"
git status --short
Write-Host "`nLatest commit:"
git log -1 --oneline --decorate
Write-Host "`nPhase 1.6.7 certification completed successfully."
