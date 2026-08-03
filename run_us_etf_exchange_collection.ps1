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

$ManifestPath = ".\data\staged\$OperatingDate\collection_manifest.json"
$CandidatePath = ".\data\staged\$OperatingDate\us_etf_discovery_candidates.json"
$QuarantinePath = ".\data\quarantine\$OperatingDate\us_etf_discovery_quarantine.json"

foreach ($RequiredPath in @($ManifestPath, $CandidatePath, $QuarantinePath)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Expected collection output was not created: $RequiredPath"
    }
}

$Manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$Candidates = @((Get-Content $CandidatePath -Raw | ConvertFrom-Json) | ForEach-Object { $_ })
$Quarantine = @((Get-Content $QuarantinePath -Raw | ConvertFrom-Json) | ForEach-Object { $_ })

if ([int]$Manifest.candidate_count -ne $Candidates.Count) {
    throw "Manifest candidate count does not match parsed candidate records."
}
if ([int]$Manifest.quarantine_count -ne $Quarantine.Count) {
    throw "Manifest quarantine count does not match parsed quarantine records."
}

Write-Host "`nCollection summary:"
Write-Host "Sources collected:      $($Manifest.source_count)"
Write-Host "ETF candidates:         $($Candidates.Count)"
Write-Host "Quarantined records:    $($Quarantine.Count)"

Write-Host "`nFirst 20 ETF candidates:"
$Candidates |
    Select-Object -First 20 symbol, security_name, primary_exchange, candidate_state |
    Format-Table -AutoSize

Write-Host "`nChecking seed ETFs:"
foreach ($Symbol in @("VOO", "SCHD", "QQQM")) {
    if ($Candidates | Where-Object { $_.symbol -eq $Symbol }) {
        Write-Host "PASS: $Symbol found."
    }
    else {
        Write-Warning "$Symbol was not found in the exchange candidate inventory."
    }
}

Write-Host "`nCollection manifest:"
Get-Content $ManifestPath

Write-Host "`nGenerated raw, staged, and quarantine files are intentionally ignored by Git."
