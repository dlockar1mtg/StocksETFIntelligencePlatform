$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

$ExpectedBranch = "phase-3-returns-benchmarks-risk"
$CurrentBranch = (git branch --show-current).Trim()

if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Phase 3.1 certification must run on '$ExpectedBranch'. Found '$CurrentBranch'."
}

python -m scripts.certify_phase_3_1_historical_data_authority

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.1 historical data authority certification failed."
}
