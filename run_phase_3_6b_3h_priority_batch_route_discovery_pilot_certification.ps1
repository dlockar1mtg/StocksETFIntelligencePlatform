$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3h_priority_batch_route_discovery_pilot

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3h certification failed."
}
