$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m scripts.certify_phase_3_2_historical_market_data_collection

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.2 historical market data collection certification failed."
}
