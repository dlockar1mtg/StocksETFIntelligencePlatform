$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3g_priority_batch_source_route_resolution

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3g certification failed."
}
