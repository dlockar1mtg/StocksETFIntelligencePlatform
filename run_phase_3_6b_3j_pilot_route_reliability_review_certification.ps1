$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3j_pilot_route_reliability_review

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3j certification failed."
}
