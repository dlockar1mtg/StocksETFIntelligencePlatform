param(
    [string]$OperatingDate = (Get-Date -Format "yyyy-MM-dd"),
    [int]$MaxRecords = 0,
    [double]$DelaySeconds = 0.25,
    [switch]$RetryFailed
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedBranch = "phase-1.6-robinhood-etf-universe"
$CurrentBranch = (git branch --show-current).Trim()
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

$InputFile = ".\data\staged\$OperatingDate\us_etf_discovery_candidates.json"
if (-not (Test-Path $InputFile)) {
    throw "Exchange candidate file not found: $InputFile"
}

$Arguments = @(
    "-m", "scripts.collect_robinhood_availability",
    "--operating-date", $OperatingDate,
    "--input-file", $InputFile,
    "--output-root", ".\data",
    "--delay-seconds", $DelaySeconds
)
if ($MaxRecords -gt 0) {
    $Arguments += @("--max-records", $MaxRecords)
}
if ($RetryFailed) {
    $Arguments += "--retry-failed"
}

Write-Host "Collecting Robinhood availability evidence..."
Write-Host "Operating date: $OperatingDate"
Write-Host "Maximum records: $(if ($MaxRecords -gt 0) { $MaxRecords } else { 'ALL' })"
Write-Host "Delay seconds: $DelaySeconds"
Write-Host "Retry failed: $($RetryFailed.IsPresent)"

& python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Robinhood availability collection failed."
}

$ManifestPath = ".\data\staged\$OperatingDate\robinhood_availability_manifest.json"
if (-not (Test-Path $ManifestPath)) {
    throw "Robinhood availability manifest was not generated: $ManifestPath"
}

$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
Write-Host "`nRobinhood collection summary:"
Write-Host "Input candidates:       $($Manifest.input_candidate_count)"
Write-Host "Completed records:      $($Manifest.completed_count)"
Write-Host "Broker eligible:        $($Manifest.broker_eligible_count)"
Write-Host "Failed lookups:         $($Manifest.failed_lookup_count)"
Write-Host "`nStatus counts:"
$Manifest.status_counts | Format-List
Write-Host "`nGenerated files are intentionally ignored by Git."
