# Market Live Validation Report

Generated: 2026-02-17T16:31:55.195403+00:00

## Checklist

- [PASS] run_and_save.py --all --output-dir out
- [PASS] Canonical store file exists
- [PASS] artifact_version == v2
- [PASS] metadata.pipeline_timestamp present and ISO
- [PASS] metadata.data_source not mock/scenario (LIVE)
- [PASS] All symbol rows: band in A/B/C/D
- [PASS] All symbol rows: band_reason non-empty
- [PASS] Wrote decision_<ts>_canonical_copy.json
- [PASS] Wrote TRUTH_TABLE_V2.md
- [FAIL] GET /api/ui/system-health
  - status=-1

## Result

**FAIL** — 1 failure(s): system-health non-200

## Outputs

- Canonical store: `C:\Development\Workspace\ChakraOps\out\decision_latest.json`
- Truth table: `C:\Development\Workspace\ChakraOps\out\TRUTH_TABLE_V2.md`
- Canonical copy: `C:\Development\Workspace\ChakraOps\out\decision_2026-02-17T163153Z_canonical_copy.json`
