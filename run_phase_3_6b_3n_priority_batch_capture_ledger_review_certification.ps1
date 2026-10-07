$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3n_priority_batch_capture_ledger_review

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3n certification failed."
}
