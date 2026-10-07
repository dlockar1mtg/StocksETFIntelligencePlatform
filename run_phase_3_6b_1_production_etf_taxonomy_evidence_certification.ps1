$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m scripts.certify_phase_3_6b_1_production_etf_taxonomy_evidence

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.1 certification failed."
}
