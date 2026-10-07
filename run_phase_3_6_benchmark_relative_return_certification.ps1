$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6_benchmark_relative_return

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6 benchmark relative-return certification failed."
}
