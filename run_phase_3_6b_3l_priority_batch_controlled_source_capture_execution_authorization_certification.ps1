$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m scripts.certify_phase_3_6b_3l_priority_batch_controlled_source_capture_execution_authorization

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3l certification failed."
}
