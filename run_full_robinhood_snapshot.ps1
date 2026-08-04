param(
    [string]$OperatingDate = (Get-Date -Format "yyyy-MM-dd")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedBranch = "phase-1.6-robinhood-etf-universe"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

$RequiredPaths = @(
    ".\data\staged\$OperatingDate\us_etf_discovery_candidates.json",
    ".\data\staged\$OperatingDate\collection_manifest.json",
    ".\data\staged\$OperatingDate\robinhood_availability_records.jsonl",
    ".\data\staged\$OperatingDate\robinhood_availability_manifest.json"
)
foreach ($Path in $RequiredPaths) {
    if (-not (Test-Path $Path)) {
        throw "Required snapshot input not found: $Path"
    }
}

Write-Host "Building governed full Robinhood ETF universe snapshot..."
Write-Host "Operating date: $OperatingDate"
python -m scripts.build_full_robinhood_snapshot `
    --operating-date $OperatingDate `
    --data-root .\data
if ($LASTEXITCODE -ne 0) {
    throw "Full Robinhood snapshot build failed."
}

$SnapshotPath = ".\data\certified\$OperatingDate\robinhood_full_universe_snapshot.json"
if (-not (Test-Path $SnapshotPath)) {
    throw "Expected snapshot was not created: $SnapshotPath"
}
$Snapshot = Get-Content $SnapshotPath -Raw | ConvertFrom-Json
Write-Host "`nSnapshot summary:"
Write-Host "Snapshot ID:          $($Snapshot.snapshot_id)"
Write-Host "Status:               $($Snapshot.snapshot_status)"
Write-Host "Total records:        $($Snapshot.counts.total_records)"
Write-Host "Broker eligible:      $($Snapshot.counts.broker_eligible)"
Write-Host "Blocked:              $($Snapshot.counts.blocked)"
Write-Host "Analytics eligible:   $($Snapshot.counts.analytics_eligible)"
Write-Host "`nGenerated certified data remains intentionally outside Git."
