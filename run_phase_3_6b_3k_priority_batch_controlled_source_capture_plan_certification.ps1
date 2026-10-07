$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

python -m scripts.certify_phase_3_6b_3k_priority_batch_controlled_source_capture_plan

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3k certification failed."
}
