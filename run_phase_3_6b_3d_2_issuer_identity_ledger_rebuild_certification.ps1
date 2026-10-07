$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3d_2_issuer_identity_ledger_rebuild

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3d.2 certification failed."
}
