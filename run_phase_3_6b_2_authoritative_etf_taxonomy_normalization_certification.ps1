$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m scripts.certify_phase_3_6b_2_authoritative_etf_taxonomy_normalization

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.2 authoritative taxonomy normalization certification failed."
}
