$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_3d_evidence_backed_issuer_identity

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3d evidence-backed issuer identity certification failed."
}
