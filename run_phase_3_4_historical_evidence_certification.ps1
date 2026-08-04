$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

python -m scripts.certify_phase_3_4_historical_evidence

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.4 historical evidence certification failed."
}

$ReportPath = ".\artifacts\certification\phase_3_4_historical_evidence_certification.json"
$Report = Get-Content $ReportPath -Raw | ConvertFrom-Json

if ($Report.status -ne "PASS") {
    throw "Phase 3.4 certification report did not return PASS."
}

Write-Host "Phase 3.4 historical evidence certification: PASS"
Write-Host "Tests executed: $($Report.tests_run)"
Write-Host "Report: $((Resolve-Path $ReportPath).Path)"
