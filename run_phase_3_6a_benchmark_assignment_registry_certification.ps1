$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m scripts.certify_phase_3_6a_benchmark_assignment_registry

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6a benchmark assignment registry certification failed."
}
