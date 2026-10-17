# ADR-0001 — Industrial Product Foundation and Bounded Rework

**Status:** PROPOSED — pending technical owner + Mine Operations/Safety signoff for safety-critical behavior  
**Date:** 2026-10-17  
**Hardware boundary:** NVIDIA Jetson Orin NX 16GB (exact carrier, JetPack, BSP and power profile still unverified)

## Context

The imported code is a valuable prototype with working concepts for GPS aggregation, camera intake, vlog segmentation, cabin behavior and evidence. The static production audit found P0 correctness and operational risks. The business target is a repeatable, commercial-grade mining edge system that can be commissioned, monitored, updated, rolled back and investigated in the field.

**Decision:** architectural rework is explicitly allowed wherever measured failure or unacceptable structural coupling requires it. We will **not** optimize around legacy class boundaries merely for backward compatibility; we preserve stable domain/event contracts, implement regression parity and migrate behind adapters. No wholesale rewrite without demonstrated migration tests. The phase sequence is risk-first, not a feature-showcase plan.

## Non-negotiable product invariants

1. **Evidence before inference:** front recording retains priority. A slow/crashed model must not block camera capture, finalize recorded segments or fill unbounded RAM. Recording gaps must be visible.
2. **Distinct physical cameras:** front and cabin have unique stable identifiers, lens settings, source contracts and health. Cabin fatigue never defaults to a front stream.
3. **Single capture ownership per camera:** encoded video can be tee'd/passthrough-recorded when supported; decode only as needed. Sharing and zero-copy are measured, not assumed. Separate OS processes are an operational choice, not a requirement for every logical module.
4. **Time & truth:** media PTS and segment boundaries anchor recording; monotonic time + UTC epochs correlate GPS/detector outputs with bounded age and uncertainty. GPS is UNKNOWN/STALE when necessary, not silently valid.
5. **Canonical typed and versioned messages:** camera frame reference, fresh GPS, detector observation, track, domain event, alert transition, segment, evidence manifest, device health. Rules never depend directly on OpenCV frame arrays or browser presentation.
6. **Alert lifecycle must be deterministic:** observed -> candidate -> active -> closed -> evidence pending -> evidence verified or explicitly incomplete/failed. Event state persists across restart; rules are versioned, have hysteresis and replay coverage.
7. **Raw recording is immutable:** stored original segments are hash-addressed/auditable; VTT, review clip and permanent overlay are derived artifacts. Mark VERIFIED only after file finalization, decode/probe and manifest validation.
8. **Safety semantics:** classification confidence is not distance and object detection is not collision avoidance. Loss of perception must report DEGRADED/UNKNOWN, never "safe". Any intervention requiring safety-critical control demands separate engineering, hazard analysis and appropriate validation.
9. **Bounded resources:** storage quotas, reserved room for evidence/metadata, backpressure, network offline store-forward, thermal headroom and visible status for dropped frames/health.
10. **Reproducibility:** deterministic image/dependencies/model hashes, per-device config, provisioning, authenticated APIs, signed artifacts, staged fleet rollout, rollback and support telemetry.

## Logical boundaries (not eight mandatory microservices)

```text
Camera Source Owners (front, cabin)
   |-- encoded raw / vlog recorder -> Segment Journal -> Verified Footage Index
   |-- live preview                    [best effort / shed first]
   |-- decoded GPU frames -> inference adapters (front objects / cabin fatigue)
                                      |
GPS / modem bridge -> validated GPS -> Canonical Observation and Time Bus
                                      |
                     Rules / Alert State / Storage Journal
                                      |
           Evidence Composer + Manifests + Retention Policy
                                      |
              Authenticated API + Fleet Agent + OTA
```

**Boundary rule:** deploy a small number of fault-isolated components where needed (e.g. recording, perception and management); avoid turning every logical concern into an RPC microservice. Local IPC may be versioned message transport or database-backed journal; each must define delivery/restart/backpressure semantics. Camera recording and inference MUST have an intentional fault-containment boundary.

## Technology-selection policy

- Camera/video: GStreamer with verified on-board codec capabilities, stable source identification, journaled segmentation and corruption recovery. Determine when encode passthrough is possible. NVIDIA hardware decode/encode only when GStreamer pipeline and loaded plugins prove it.
- Perception: benchmark DeepStream + TensorRT FP16 model candidates on *the exact Jetson image*. Try NVIDIA DashCamNet first as one baseline, compare with license-approved YOLO and optional specialist models. DeepStream/JetPack pairing cannot be decided from a version name alone; confirm NVIDIA matrix and carrier BSP compatibility.
- Cabin fatigue: preserve baseline business event semantics via versioned observation adapter while selecting/validating a supported inference runtime, not calling CPU MediaPipe "GPU".
- Data plane: per-camera PTS epochs, monotonic correlation and local append-only event/recording journal. SQLite may be valid when engineered for WAL, crash behavior, bounded writes and backups; do not add a remote database to local recording's critical path.
- Control plane: local-first fleet configuration, signed staged OTA, health, metrics and remote debugging with consent/access control.
- Evidence: raw video + canonical sidecar are authoritative; generated overlay video is optional and cannot overwrite raw.

## Allowed refactor strategy

| Legacy area | Approach |
|---|---|
| Domain logic, redis payload, GPS business mapping | KEEP / isolate adapters, fix stale validity |
| CameraCV2 and in-process unbounded frame copying | REWORK/REPLACE after frame ownership and benchmark proof |
| OpenVINO 'GPU' assumption | REPLACE with validated NVIDIA backend |
| Cabin fatigue rules | KEEP contract, port detector incrementally with replay comparison |
| SQLite and event metadata | HARDEN transaction and consistency; don't replace solely for novelty |
| Current web review UI | KEEP where workable, HARDEN security and honest health indicators |
| Sidecar and overlay | REWORK around canonical PTS and immutable evidence |
| Fleet lifecycle | BUILD deliberately; no silent deployments |

## Safety and commercial restrictions

MH02 is currently a **prototype, NOT a certified collision-avoidance or functional-safety system**. Mine Operations and Safety must sign off: intended use, severity taxonomy, warning thresholds, failure indication, camera locations, alert escalation, privacy and validation scenarios. Certifications/standards, required sensors and legal obligations need specialist review, not automated claims. Distribute only approved dependencies, model weights, footage and licenses.

## Acceptance + reversible migration

1. Reproduce known P0 failures as deterministic tests and record baseline.
2. Implement corrected event and clock contracts with adapters and versioned schema; compare replay outputs.
3. Separate recording from inference; inject camera disconnect, power-cycle and disk-full scenarios.
4. Ship mine-domain detector behind feature flag to 1 canary; assess by known model checksum.
5. Harden per-unit installation, auth, provisioning, OTA/rollback and support documentation.
6. Complete bench soak, field canary, hazard/operations review and commercial license review before release.

Every phase has explicit rollback to last VERIFIED build; never roll back a schema without migration compatibility. A passing CI syntax check is **not** release acceptance.

## Rejected approaches

- A total immediate rewrite: too much feature-parity and evidence-continuity risk before hardware proof.
- Keeping OpenCV/NumPy in the primary path simply because it currently works: unknown compute and copy cost.
- One giant process that treats inference, recording, evidence and web as inseparable.
- Claiming detections as "collision avoidance" or using production default-green degraded states.
- Pinning latest JetPack/DeepStream without verifying BSP and camera interoperability.

## References

- [Research and product gap matrix](../../research/competitive-reference-study.md)
- [Existing target architecture](../target-architecture.md)
- [Production readiness audit](../../audits/2026-10-17-production-readiness.md)
- [Release gates](../../operations/release-gates.md)
