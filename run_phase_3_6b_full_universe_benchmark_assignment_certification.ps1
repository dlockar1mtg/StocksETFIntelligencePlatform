$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_6b_full_universe_benchmark_assignment

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b full-universe benchmark assignment certification failed."
}
