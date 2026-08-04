$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

python -m scripts.certify_phase_3_5_total_return_calculation

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.5 total-return calculation certification failed."
}
