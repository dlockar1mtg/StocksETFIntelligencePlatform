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

$RepositoryRoot = (Get-Location).Path
$CollectorModule = "scripts.collect_us_etf_exchange_universe"

Write-Host "Collecting authoritative US exchange-listed ETF candidates..."
Write-Host "Operating date: $OperatingDate"
Write-Host "Repository root: $RepositoryRoot"

python -m $CollectorModule `
    --operating-date $OperatingDate `
    --output-root .\data

if ($LASTEXITCODE -ne 0) {
    throw "US ETF exchange collection failed."
}

$Manifest = ".\data\staged\$OperatingDate\collection_manifest.json"
if (-not (Test-Path $Manifest)) {
    throw "Expected collection manifest was not created: $Manifest"
}

Write-Host "`nCollection manifest:"
Get-Content $Manifest

Write-Host "`nGenerated files are intentionally ignored by Git."
