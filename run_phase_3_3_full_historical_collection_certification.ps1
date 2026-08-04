$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_3_full_historical_collection

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.3 certification failed."
}
