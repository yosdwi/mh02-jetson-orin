# MH02 Jetson Orin NX 16GB — Edge Video & Detection

> **Status: PROTOTYPE / NO-GO for mass production.** Baseline imported from the uploaded `mh02model.zip` (2026-10-17). This is *not* a proven deployment image. No real Jetson acceptance test was executed here.

## Scope

- **Front**: independent vlog / segmented recording, live preview, planned pedestrian + vehicle inference.
- **Cabin**: independent fatigue pipeline (closed eyes, yawning); current CPU-compatible implementation needs source/freshness correction.
- **Shared**: GPS/aggregate/events, recording/alert evidence, WebVTT, web playback and fleet operation.
- **Target hardware**: **NVIDIA Jetson Orin NX 16GB**; do **not** assume a JetPack/DeepStream release without checking the actual device/carrier board.

## Current source

- `mh02model/runtime/`: Python service prototype + systemd + MediaMTX + web.
- `mh02model/apps/mh02/`: legacy business logic, camera/video processors and Jetson GStreamer POC.
- `mh02model/files/configs/*.example`: sanitized **reference only**; do not treat as device-ready configuration.

## Start here

1. [`AGENTS.md`](AGENTS.md) — mandatory rules for all coding agents.
2. [`docs/architecture/target-architecture.md`](docs/architecture/target-architecture.md) — target topology and invariants.
3. [`docs/audits/2026-10-17-production-readiness.md`](docs/audits/2026-10-17-production-readiness.md) — P0/P1 static audit, evidence and acceptance gates.
4. [`docs/audits/2026-10-17-orin-nx-16gb-addendum.md`](docs/audits/2026-10-17-orin-nx-16gb-addendum.md) — hardware-specific addendum (version claims require live revalidation).
5. [`docs/operations/release-gates.md`](docs/operations/release-gates.md) — go/no-go criteria.
6. [`.agents/skills/`](.agents/skills/) — task-specific agent workflows.

## Industrial productization plan (proposed)

- [Industrial architecture ADR](docs/architecture/adr/0001-industrial-product-foundation.md) — permitted rework, capture ownership, data/evidence integrity and safety boundaries.
- [Competitive reference study](docs/research/competitive-reference-study.md) — Blaxtair, Hexagon, Netradyne, Cat and NVIDIA comparisons; KEEP/ADOPT/ADAPT/RESEARCH matrix.
- [Industrial readiness roadmap](docs/operations/industrial-readiness-roadmap.md) — milestone order, acceptance evidence, ownership and first regression-test batch.

Documentation records decisions and evaluation criteria; **it does not mean deployment, GPU acceleration, model quality or safety certification has been demonstrated.**

## Safety / publication notes

The source archive included RTSP credentials and local deployment identifiers. These were **not** published. Device/environment configuration was converted to `.example` templates; a legacy RTSP probe was switched to environment-based config. Windows EXE/DLL/WAV artifacts, generated Python cache and transient logs were excluded. See [`docs/operations/import-manifest.md`](docs/operations/import-manifest.md).

Never put a deployed camera URI, password, API token, GPS trace, employee/driver identity or recorded footage in this public repository. Model weights and third-party binaries require provenance and licensing review.

## Local checks (not substitutes for Jetson acceptance)

```bash
python3 -m compileall -q mh02model/apps/mh02 mh02model/runtime/mh02_runtime
python3 mh02model/apps/mh02/jetson_gstreamer_runtime.py --camera-id front --dry-run --print-pipeline
```

## Change policy

Only additive docs/source-import changes in this baseline; no hardware/performance/production claims without on-device evidence. Use protected PR review for future runtime changes. See `AGENTS.md` and the release gates.
