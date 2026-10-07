$ErrorActionPreference = "Stop"

python -m scripts.certify_phase_3_6b_3p_sec_series_class_specific_filing_resolution

if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3p certification failed."
}
