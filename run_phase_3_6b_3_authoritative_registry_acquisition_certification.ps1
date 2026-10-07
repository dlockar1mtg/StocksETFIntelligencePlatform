$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m scripts.certify_phase_3_6b_3_authoritative_registry_acquisition
if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3 authoritative registry acquisition certification failed."
}
