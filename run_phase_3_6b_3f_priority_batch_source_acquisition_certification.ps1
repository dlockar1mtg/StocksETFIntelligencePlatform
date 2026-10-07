$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3f_priority_batch_source_acquisition

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3f certification failed."
}
