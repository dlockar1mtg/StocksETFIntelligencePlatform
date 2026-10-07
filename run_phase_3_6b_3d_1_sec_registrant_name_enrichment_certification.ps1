$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
python -m scripts.certify_phase_3_6b_3d_1_sec_registrant_name_enrichment
if ($LASTEXITCODE -ne 0) { throw "Phase 3.6b.3d.1 certification failed." }
