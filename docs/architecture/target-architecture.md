# MH02 Edge — Target Architecture v0.1 (Proposed)

**Status:** Architecture proposal / not an implementation claim. **Device:** Jetson Orin NX 16GB. Device-specific JetPack, DeepStream, carrier BSP and exact camera capabilities remain to be inventoried.

## Functional decomposition

```text
Front camera ──[single source owner]──┬── original vlog segmentation (immutable)
                                      ├── live preview (shed first)
                                      └── DeepStream/TensorRT -> person/vehicle track metadata

Cabin camera ──[single source owner]──┬── optional raw cabin evidence/preview
                                      └── fatigue inference -> eyes/yawn observations

GPS/modem/Redis ── single GPS adapter ── validated fresh location samples
                                      │
             Media PTS + monotonic/UTC mapping + boot epochs
                                      │
                Canonical typed event/aggregate store
                   ├── policy/rule engine (freshness + hysteresis)
                   ├── alert state machine + pre/post video references
                   ├── datalog/retention/health
                   └── evidence exporter (raw hashes, VTT, optional overlay MP4)
                                      │
               Authenticated local API/media + fleet uploader/OTA
```

## Design invariants

1. **Recording priority:** front vlog cannot depend on inference completion or browser/web process; failures are reported as coverage gaps, never silently hidden.
2. **Camera routing:** `front` means road; `cabin` means driver. No fallback of fatigue to front. Each camera has own stable device identity and stream health.
3. **Clock:** video frame PTS/segment boundaries authoritative; UTC correlation, error/uncertainty and clock epoch explicit. GPS validity includes age, fix quality, timestamp and coordinate sanity.
4. **Data contracts:** versioned `CameraFrameRef`, `GpsFix`, `DetectorObservation`, `DomainEvent`, `RecordingSegment`, `EvidenceManifest`, `DeviceHealth`. Field units documented, e.g. `speed_kmh`, `distance_m`, `timestamp_utc`, `media_pts_ns`.
5. **Storage:** no unbounded local disk, queue or frame cache. Reserve space for alert evidence and journaling; enforce retention with pinned/legal-hold rules.
6. **Evidence:** `raw_hash` and `derived_hash`; sidecar VTT/ASS/overlay are renderings of canonical synchronized data; verify emitted MP4 with media tools before status VERIFIED.
7. **Safety:** inference unavailable ≠ no hazard. Detection is an observation; risk rules and warning sensitivity are separately validated in mine domain.
8. **Ops:** systemd restart budgets, health probes for camera/recording/inference/GPS, CPU/memory/encoder/thermal monitoring, OTA canary/rollback and full source-to-release provenance.

## Proposed event contract

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "boot_id": "uuid",
  "unit_id": "redacted-stable-id",
  "camera_id": "front",
  "frame_id": "monotonic-camera-sequence",
  "media_pts_ns": 0,
  "observed_at_utc": "2026-10-17T00:00:00Z",
  "utc_uncertainty_ms": null,
  "source_age_ms": 0,
  "detection": {"type":"person","confidence":0.9,"track_id":"x","bbox_xyxy":[0,0,1,1]},
  "gps": {"status":"NO_FIX","fix_age_ms":null},
  "model_version": "unverified",
  "rule_version": "unverified",
  "recording_segment_id": null
}
```

The JSON is a **design example**, not a schema implemented by existing source.

## Inference selection (benchmark, not product decision)

Compare NVIDIA DashCamNet, PeopleNet+TrafficCamNet and licensing-cleared small YOLO TensorRT FP16 on annotated mine-site sequences. Profile simultaneous 1080p vlog, live streaming, front inference, cabin fatigue, aggregate/store and evidence export; report throughput, p95 latency, missed frames, recall and false alarms by operating scenario. INT8 only after calibrated FP16 accuracy parity. Avoid pinning versions until Jetson BSP/camera interoperability checked.

## Migration slices

1. P0 correctness: stale fatigue and GPS, source IDs and clock mapping, lifecycle, tests.
2. P0 raw recording integrity/recovery, storage policies and auth.
3. Production dual-camera routing and low-copy GPU path with field instrumentation.
4. TensorRT detector benchmark and mine-specific calibrated events.
5. Cabin parity, derived overlay rendering and fleet staged rollout/rollback.

See [`audit`](../audits/2026-10-17-production-readiness.md) and [`release gates`](../operations/release-gates.md).
