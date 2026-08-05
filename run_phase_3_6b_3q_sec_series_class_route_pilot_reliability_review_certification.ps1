$ErrorActionPreference = "Stop"

python -m scripts.certify_phase_3_6b_3q_sec_series_class_route_pilot_reliability_review

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3q certification failed."
}
