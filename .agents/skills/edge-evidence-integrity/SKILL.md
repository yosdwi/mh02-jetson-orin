# Skill: Edge Event and Evidence Integrity

Use for GPS/fatigue event lifecycle, timestamps, VTT, clip export, overlay and retention changes.

## Workflow
1. Draw source lineage: frame PTS → segment timestamps → aggregate GPS fixes → detector observations → alert rules → clip input segments → evidence manifest.
2. Reproduce stale signal and clock-shift cases with deterministic fake clocks and fixed samples; add regression first.
3. Encode explicit freshness TTL and fix quality. GPS/fatigue `STALE/UNKNOWN` must not be treated as live/clear or cause new alert.
4. Verify segment `OPEN/FINALIZING/VERIFIED/PUBLISHED`, media decode/PTS, CRC/SHA256 and atomic persistence. Report failures as incomplete, never complete.
5. Test clip spanning 2–3 segments, missing post window, missed keyframe boundary, reboot mid-export, duplicates and idempotency.
6. Preserve raw MP4. Render optional human-readable burn-in as derived asset with source references, metadata snapshots, render version and hashes; ensure VTT no overlapping cues.

## Done only when
Same canonical source yields deterministic event output and traceable video/metadata, real file validity checked, mismatch/gap flagged and original video untouched.
