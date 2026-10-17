# Industrial Product Readiness Roadmap — Jetson Orin NX 16GB

**Status:** proposed execution baseline, not a commitment that the system is already production-ready.  
**Owner signoffs needed:** Edge Engineering, Mine Operations, Safety, Cybersecurity/IT, Product/Commercial.

## Milestone A implementation checkpoint — 2026-10-17

The current `main` implementation includes a versioned Pydantic runtime configuration store with validation, history, rollback and an allowlisted restart API; explicit front/cabin camera routes and systemd owners; JSON journald formatting plus a persistent-retention example; and a web test lab with deterministic isolated fatigue simulations, live-cabin fail-closed behavior, report persistence, camera selection and diagnostics bundles. Regression coverage exercises these paths through the FastAPI surface.

This checkpoint is locally verified only. The physical Jetson inventory still has one UVC camera, no verified cabin publisher, and no deployed copy of these changes. Therefore dual-camera capture, live cabin fatigue, persistent journald behavior, service restart execution and hardware recording continuity remain unverified and are not release claims. The example configuration uses stable placeholder camera by-id paths until commissioning maps real devices.

### Milestone B implementation checkpoint — DeepStream adapter

The source now includes a disabled-by-default DeepStream 6.2/TensorRT front adapter with live RTSP and MP4 replay modes, `nvinfer`/`nvtracker` graph construction, typed detection and advisory-warning artifacts, model digest capture, health metrics and web validation/overlay surfaces. It fails closed when runtime plugins, `pyds`, model assets or tracker configuration are absent, and it does not own recording. The measured Jetson tuple is L4T R35.3.1 / JetPack 5.1.1, CUDA 11.4, TensorRT 8.5.2 and GStreamer 1.16.3; an isolated user-space DeepStream extraction is the only permitted deployment path for this checkpoint.

This checkpoint is not a claim that Milestone B is complete. It becomes evidence-backed only after the target loads the NVIDIA plugins, runs an approved TensorRT engine on live front and authorized MP4 input, and records GPU/FPS/latency/memory/recording-continuity artifacts. DashCamNet weights/engine redistribution terms and a second physical cabin camera are currently commissioning dependencies.

## P0 frame synchronization checkpoint — 2026-10-18

Commits `b3810d5`, `558e294`, `59d8a60`, `211e01e`, and `ac277fc` add the versioned `FrameRef` contract, stream-epoch/frame-sequence identity manager, exact Cabin `FrameResultJoiner`, branch-local duplicate-PTS handling, Front `NvDsFrameMeta.frame_num` timing correlation, bounded asynchronous Front artifact persistence, a background telemetry cache, and explicit p50/p95/p99 inference health fields. OSD callbacks no longer call `RuntimeStore.latest_aggregate()`. Unmatched Front PTS values are reported as unknown latency; an unrelated pending frame is never consumed as a fallback.

Automated validation: `PYTHONPATH=mh02model/runtime pytest -q` passed 41 tests, with coverage for out-of-order and late inference, camera/epoch contamination, duplicate/missing/discontinuous PTS, future/stale telemetry, and Front frame-number latency correlation. Python compileall and `git diff --check` also passed.

Development Jetson evidence: the user-space DeepStream 6.2 plugins and `pyds` loaded on the L4T R35.3.1 / JetPack 5.1.1 device. After the Front service restart, `front-health.json` reported `frames=5968`, `fps=28.7356`, `dropped_frames=0`, `unmatched_latency_frames=0`, `duplicate_pts=0`, `pts_discontinuities=0`, and `missing_pts=0`; the sample engine reported zero detections in that window, so detector coverage is not claimed. `gst-discoverer-1.0` identified `/front-annotated` as live H.264 1920x1080. A longer `gst-launch` decode probe timed out with Jetson `Stream format not found` drops and is therefore not a decode PASS. Clean `mh02-vlog.service` remained active and finalized Front MP4 files continued to grow. `tegrastats` observed roughly 5.1–5.3 GB RAM used, GR3D samples of 0–44%, and GPU/CPU-system temperatures about 56–62 C during the window.

Cabin remains BLOCKED on physical evidence: the device exposes one UVC camera identity with `/dev/video0` and `/dev/video1`, no verified `/cabin` publisher, and `mh02-cabin-annotation.service` is intentionally inactive in the development configuration. GPS hardware was serial-accessible but observed as `GPS NO SIGNAL / FIX_EXPIRED`; historical coordinates were not treated as live overlay data. p50/p95/p99 end-to-end latency and encoded overlay pixel inspection remain unverified.

The rollback reference for the staged device deployment is `/home/smartd/mh02_backups/p0-frame-sync-20261018T180025Z-before-frame-num`; restore its `runtime-before` tree, run `systemctl daemon-reload` if units are changed, and restart only the affected inference service. Do not remove recordings or SQLite state.

## Product scope / definition of done

Commercial MH02 includes: front 24/7-capable vlog with bounded local retention; front pedestrian/vehicle observations and governed warnings; separate cabin closed-eyes/yawning; tamper-evident review evidence; validated GPS timestamp correlation; device commissioning, authenticated management, telemetry, controlled updates and rollback.

**NO-GO until proven:** source/freshness correctness, recording integrity, watchdog and fault recovery, security, storage/thermal envelope, domain model performance, on-device soak, fleet pilot and licensing. The release gates document defines measured evidence requirements; reported numbers are proposed targets only.

## Delivery strategy — migrate in verified slices

| Workstream | Priority | Deliverable | Must prove before advancing |
|---|---|---|---|
| M0 Freeze/inventory | P0 | hardware + running JetPack/BSP, camera capabilities, current runtime/commit/config without secrets, reproduce original bugs; risk ledger | reproducible local tests and captured device inventory |
| M1 Correctness | P0 | typed fresh GPS/fatigue contracts, explicit front/cabin mapping, frame timestamp correlation and alert state transitions | stale data tests, time-jump/boot tests, parity fixtures |
| M2 Recorder integrity | P0 | single ingest owner, independent recorder, segment open/finalize/verify journal, gap reporting, retention quota | camera unplug, power loss, disk full, 72h record/soak and segment replay |
| M3 Production security | P0 | authenticated endpoints, secrets injection, least-privilege systemd, device identity, logs and audit trail | anonymous access denied, restart and offline stress, secret scan |
| M4 GPU path | P1 | DeepStream/TensorRT front inference while raw vlog remains independent | simultaneous front+cab workload p95/FPS/thermal/CPU/RAM and missing-frame report |
| M5 Mining object intelligence | P1 | labelled mine footage and model comparison; tracker + versioned rule engine | per-class precision/recall, FP/hour, latency and operator signoff by scenario |
| M6 Cabin DMS parity | P1 | validated cabin detector and fatigue rules with healthy/degraded states | closed-eyes/yawn regression, IR/daylight/occlusion tests, false fatigue alerts/hour |
| M7 Evidence delivery | P1 | raw + canonical metadata + review clip + optional overlay rendering + manifests | PTS/VTT synchronized, pre/post availability verified, hash replay and authorized download |
| M8 Fleet production | P0 before scale | commissioning pack, signed releases, staged rollout, telemetry, retention policy, rollback + support playbooks | canary and rollback rehearsal, 72h bench + 7-day field pilot, gate signoffs |

**Dependency note:** M3 may be developed in parallel with M1/M2, but public/demo access must not expand before authentication. M4/M5 exploration can begin without releasing ungoverned warnings. M8's fleet framework starts early, its production signoff is last.

## Audit-to-backlog conversion rules

- Every P0 finding becomes an issue with: evidence (file/function/line and reproducer), affected service, failure mode, desired state, migration plan, regression test, telemetry proof, rollback and owner.
- Classify every touched capability KEEP, REWORK, EXTRACT, DEPRECATE or SHARED.
- Use an ADR when decisions affect message formats, capture ownership, timebase, storage layout, warning semantics, network exposure, third-party inference runtime or fleet delivery.
- No unreviewed broad rewrites. PRs must show baseline vs changed behavior and distinguish simulation from hardware proof.
- Source commit, image/build hash, installed model checksum, config revision and ruleset revision must identify any field-generated evidence.

## Reference architecture interfaces (design targets)

- `CameraFrameRef`: source_id, boot_id, source generation, frame sequence, PTS/DTS and caps. No large raw frame in application-domain events.
- `GpsSnapshot`: sampled_utc, observed_monotonic, age, fix quality, position uncertainty, coordinates, speed and source state.
- `DetectorObservation`: camera_id, frame reference, class, score, bbox, track_id, model digest and measured processing delay.
- `DomainEvent`: event_id, event/rule type, lifecycle state, source freshness, site/unit configuration version, time uncertainty and evidence correlation.
- `RecordingSegment`: start/end PTS, filename, codec, state OPEN/FINALIZING/VERIFIED/PUBLISHED, byte count, hash, gap count and error.
- `EvidenceManifest`: event ID, original segment list/hashes, actual trimmed interval, derived hashes, overlay renderer revision, sync error and review status.
- `DeviceHealth`: camera/recording/inference/GPS/web status, loss counters, uptime/boot ID, storage watermark, thermals and active release.

Schema formats remain proposals until merged with tests; avoid inventing PTS-to-UTC precision.

## Engineering release acceptance — fill with recorded evidence, not checkboxes alone

For each gate provide an evidence artifact location and reviewer:
- G0 supported image and reproducible install, pinned dependencies and distributable license inventory;
- G1 business correctness under stale/corrupt/out-of-order inputs, restart and time jump;
- G2 video coverage from independently measured frame/PTS intervals, not file count alone;
- G3 resilience under camera disconnect, SSD filling, thermal/power stress, abrupt power removal and network outage;
- G4 API live/archive authorization, secret provisioning and security scan;
- G5 retention under hard quota and protected alert evidence; emergency behavior when disk unavailable;
- G6 mine-domain accuracy under day/night/dust/rain/dense traffic, false alarm rate and measured combined workload;
- G7 72h bench soak and 7-day canary with measured reliability, no invented pass;
- G8 consistent raw/derived hashes and replay of boundary-spanning alerts;
- G9 commercial deployment: signed OTA/canary/rollback, SOP installation, field support, warranty policy, component license review and Safety signoff.

Proposed KPIs (require agreed numerical thresholds before tests): verified recording coverage %, median/p95 time-to-warning, false warning/hour, per-class recall, segment corruption rate, recovery time after reconnect/reboot, peak RAM, thermal margin, SSD TB written/day and failed rollout %.

## Next implementation batch (concrete, deliberately narrow)

**Batch A — establish truths before architecture refactor**
1. Inspect Jetson `/etc/nv_tegra_release`, carrier model/BSP, camera device identities and formats, storage/power profile; do not change deployment while reading inventory.
2. Map exact running entrypoints, systemd units and data contracts from current `main` and installed device; diff deployment vs repo.
3. Add failing tests for stale fatigue event and stale GPS acceptance; reproduce wrong front/cabin routing.
4. Document actual MP4/VTT PTS/time drift with synthetic replay and signal freshness changes.
5. Land scoped P0 patches in a branch/PR with before/after regression proof and rollback notes.

**Batch B — recording subsystem**
1. Write a journalled recorder contract independent from inference; decide passthrough vs NVENC only after device capabilities are measured.
2. Create simulated camera EOS, disconnect, corrupt segment, disk-full and power-cycle fixtures.
3. Verify segment media and reserve quota; expose coverage gaps in web/API; never mark incomplete file COMPLETE.
4. Bench test raw vlog + preview + optional inference in combination.

**Batch C — detector/alert pilot**
1. Secure rights to mine-footage and annotate representative test set; identify DT/SDT taxonomy.
2. Benchmark 2–3 candidates on the target image with full concurrent workload; lock model only after measured acceptance.
3. Implement governed person/vehicle tracking and warning thresholds under feature flags; obtain operator signoff.
4. Run canary and shadow mode before enabling driver alerts.

## Decision log to settle with stakeholders

- Site operating envelope, allowed false alarm/hour, safe alert modality and whether this is only advisory vs safety-related.
- Camera count per SKU, cable type, optical FOV, night/IR, lens mounting, weather/dust protection and camera replacement behavior.
- Recording retention days, SSD endurance/capacity, protected evidence retention, privacy/role permissions and transmission budget.
- Existing physical Jetson L4T/JetPack carrier compatibility, ACC shutdown and power conditioning, container vs native install.
- Pilot fleet size, operating hours, fault scenarios, support ownership, firmware upgrade windows, and fallback criteria.
- License redistribution rights (NVIDIA model, third-party YOLO weights, FFmpeg/GStreamer binaries and models).
- Any applicable mining/earthmoving product-safety standard requires expert hazard and compliance assessment; none is presently claimed achieved.

## Pointers

- [AGENTS rules](../../AGENTS.md)
- [Product study](../research/competitive-reference-study.md)
- [Architecture ADR](../architecture/adr/0001-industrial-product-foundation.md)
- [Release gates](release-gates.md)
- [Production readiness audit](../audits/2026-10-17-production-readiness.md)
