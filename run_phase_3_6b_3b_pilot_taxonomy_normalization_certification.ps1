$ErrorActionPreference = "Stop"
python -m scripts.certify_phase_3_6b_3b_pilot_taxonomy_normalization
if ($LASTEXITCODE -ne 0) {
    throw "Phase 3.6b.3b certification failed."
}
