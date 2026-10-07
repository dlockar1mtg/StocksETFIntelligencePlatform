$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3a_issuer_source_capture_pilot

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3a certification failed."
}
