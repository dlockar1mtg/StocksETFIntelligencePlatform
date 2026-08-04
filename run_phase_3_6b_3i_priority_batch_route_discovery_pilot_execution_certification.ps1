$ErrorActionPreference = "Stop"
python -m scripts.certify_phase_3_6b_3i_priority_batch_route_discovery_pilot_execution
if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3i certification failed."
}
