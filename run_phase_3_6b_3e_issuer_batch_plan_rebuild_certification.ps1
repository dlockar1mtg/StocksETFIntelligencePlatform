$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3e_issuer_batch_plan_rebuild

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3e issuer batch plan rebuild certification failed."
}
