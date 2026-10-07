$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m scripts.certify_phase_3_6b_3c_issuer_batch_expansion

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3c issuer batch expansion certification failed."
}
