$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

python -m scripts.certify_phase_3_6b_3o_sec_product_specific_filing_document_route_remediation

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3o certification failed."
}
