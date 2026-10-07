$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepositoryRoot

python -m scripts.certify_phase_3_6b_3m_priority_batch_controlled_source_capture_execution

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
