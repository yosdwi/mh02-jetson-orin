# MH02 — Jetson Orin NX 16GB Production Baseline Addendum

**Tanggal:** 17 Oktober 2026  
**Status:** Architecture decision proposal / NO-GO mass production until board tests pass  
**Applies to:** `mh02model.zip` + previous `MH02_Jetson_Orin_Production_Readiness_Audit_2026-10-17.md`  
**Hardware confirmed by owner:** NVIDIA Jetson Orin NX 16GB. **Not yet confirmed:** carrier-board model, boot medium, camera SKU, actual JetPack/L4T, current service/version, power/thermal, deployment source repository, mine-site dataset.

## 1. Important corrections to previous audit

- P0-10 is **partially resolved**: Orin NX 16GB **does have NVIDIA NVENC/NVDEC**, so hardware video encoding is a viable architectural path. Whether the actual installed pipeline and camera support the desired modes remains **UNVERIFIED** until measured on-device. Never infer active hardware acceleration from pipeline text or a simulated dry-run.
- The previous audit's recommendation to use DeepStream 7.1 + JetPack 6.1 is a **conservative existing option**, **not the only supported option** as of October 2026.
- NVIDIA's **DeepStream 9.1** now explicitly supports **Jetson Orin NX/AGX/Nano**, with documented **JetPack 7.2 GA (L4T 39.2)** prerequisite. It should be evaluated as an alternate modern baseline, not installed over an active deployment without compatibility and rollback testing.
- JetPack **7.2.1** exists for Orin (Jetson Linux 39.2.1); **do not assume** compatibility with the exact DeepStream 9.1 package just because 7.2 GA is officially paired. Test and pin the actual working tuple including carrier BSP, kernel drivers and TensorRT engine builder.
- NVIDIA published an Orin Nano/NX `overlay_pcie.tbz2` for intermittent boot initialization problems during reboot/power cycling on JetPack 7.2. Check applicability before any fleet image freeze.

Primary sources:
- https://developer.nvidia.com/downloads/jetson-orin-nx-module-series-data-sheet
- https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_Installation.html
- https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_Release_notes.html
- https://developer.nvidia.com/deepstream-getting-started
- https://developer.nvidia.com/embedded/jetpack/downloads
- https://developer.nvidia.com/embedded/jetpack/downloads/archive-7.2

## 2. Software stack decision gates

**Track A: minimal-migration / conservative** — JetPack 6.1 + DeepStream 7.1 (NVIDIA-paired). Choose when current deployed image and vendor carrier BSP are compatible and stable. Security fixes and lifecycle policy still need explicit review.

**Track B: modern greenfield / pilot** — JetPack 7.2 GA + DeepStream 9.1 (NVIDIA-paired). Choose only if OEM carrier support, camera drivers, MediaMTX, Jetson GStreamer plugins, CUDA/TensorRT model pipeline, and OTA/rollback are verified in laboratory test. Use a separate golden image. Do **not** automatically elevate Track B to fleet release because the packages are newer.

**First action**: run *read-only inventory* on the physical Jetson, then decide which track has lower net migration risk. In both tracks, pin `BSP/L4T + JetPack + DeepStream + TensorRT + GStreamer + driver + model SHA + service version` as one tested release tuple. Create TensorRT engines in the target runtime, not blindly on a laptop or another TensorRT release.

## 3. Hardware workload envelope (initial engineering targets, not measured capability)

| Workload | Proposed initial target | Policy |
|---|---|---|
| Front vlog | 1920x1080, 30 FPS raw archive, H.264 initially | Highest priority; loss must be reported, no silent gaps |
| Front detection | Sample 10–15 FPS from decoded front feed; model input ~640px side | Inference may shed frames when overloaded, archive may not |
| Cabin detection | Separate cabin feed; sample 5–15 FPS, measured for fatigue semantics | No reuse of front stream; fail to `UNKNOWN` on missing camera |
| Preview | Lower-priority encoded preview through secured media gateway | Viewer outage must not stop recording |
| GPS/telemetry | Typed snapshots and validity/freshness, 1 Hz minimum reference | GNSS signal stale => unknown or invalid, never silently inherited |
| Alert MP4 | Derive from raw finalized segments, pre/post windows validated | Immutable parent raw; derived overlay optional with provenance |

Camera reality in supplied docs: current single USB/UVC device advertises MJPEG 1920x1080@30. For it, `v4l2src -> jpegparse -> nvv4l2decoder(mjpeg=1)` may be used if verified. For cameras delivering compressed H.264/H.265, prefer encoded archive **passthrough/remux** rather than a second lossy encode. Evaluate timestamp monotonicity/keyframes and container recovery either way.

**Power modes**: compare official supported profiles at the real carrier power supply and heat sink. Initially test a bounded sustained profile (e.g. 25 W) and profile at higher power only when available and thermally qualified; 40 W `MAXN_SUPER` is a mode on certain Orin NX 16GB Super configurations, **not** a guaranteed field-safe continuous setting. Test at expected mine ambient temperature, airflow, vibrations, startup voltage transients and power-loss behavior.

**Disk planning**: at 4 Mbit/s a single continuously recorded stream is approximately 43.2 GB/day decimal, excluding overhead; at two independent streams each 4 Mbit/s, about 86.4 GB/day. This is **illustrative**, not a measured encoder bitrate. Fleet design must set actual bitrate, allocated storage, reserved free space, archive retention, alert pin policy, write-endurance and evidence upload schedule.

## 4. Video topology (target, not a claim about current implementation)

```
 Front Camera --[stable UVC ID or RTSP endpoint]--+--> single ingest/clocked decoded feed
                                                    |      |
                                                    |      +--> DeepStream nvinfer + nvtracker -> front events
                                                    |
                                                    +--> Archive: native H264/H265 passthrough OR NVENC encode once
                                                    |      -> splitmuxsink -> FINALIZING -> VERIFIED -> PUBLISHED
                                                    +--> Bounded low-priority preview branch -> MediaMTX

 Cabin Camera --[independent stable source]---------> cabin ingest -> cabin evidence/archive policy
                                                               -> fatigue inference
                                                               -> fresh frame-bound events

 GPS/telemetry store ----> clock mapper (boot_epoch, PTS, UTC, uncertainty) ---> canonical event log

 Canonical events + verified raw segments -> alert clip assembler -> hash/manifest
                                          -> deterministic overlay derived clip (optional)
                                          -> authenticated API/upload/fleet health
```

Invariant: one owner of each capture device; per-branch queue/backpressure explicit. On inference failure raw recording stays healthy; on camera failure, events cease being fresh and coverage gaps appear. For source-loss detection track last frame PTS and camera heartbeat separately from process health.

## 5. Front detector model selection — NVIDIA-first benchmark

**Baseline A: NVIDIA TAO DashCamNet**. One model already detects **person, car, two-wheeler and road sign** from dashcam-like inputs; suitable first end-to-end DeepStream + TensorRT proof, but its pretraining is not a reliable mining-truck or excavator classifier without mine-site evaluation/fine-tuning. NVIDIA lists limitations for low light, occlusion, small objects and geographic domain shift. This NVIDIA model's intended use is **not** an already certified collision-warning safety subsystem.

**Baseline B: NVIDIA PeopleNet + TrafficCamNet**. Two specialized detectors, may improve person/vehicle class-specific recall but costs additional inference resources and integration. Use only if A underperforms in classes that matter.

**Baseline C: YOLO11n or comparable small one-pass detector -> ONNX -> TensorRT FP16**. One model can cover `person`, `car`, `truck`, `bus`, `motorcycle` as pretrained class names but mine-site semantics need labeling/remapping (`pedestrian`, `DT`, `SDT`, `LV`, `excavator`, etc.). Use only after validating export preprocessing/NMS and commercial license. Ultralytics official licensing says commercial/proprietary deployment typically requires Enterprise or AGPL compliance; complete a legal review before considering it a production default.

**Primary pilot recommendation**: start with A for an NVIDIA-native functioning reference and C for an alternate unified-model benchmark. Choose by per-class recall, false positives, night/dust failure modes, p95 end-to-end latency, sustained CPU/GPU/NVENC utilization, RAM use, energy and thermal headroom; do not choose by FPS or generic COCO mAP alone.

**Risk logic**: object detection != collision risk. Require separately validated road ROI, camera calibration, temporal tracking, speed/GPS validity, object trajectory and false-alarm policy. Do not use raw bbox width as physical distance/TTC. An inference failure or insufficient confidence should produce **UNKNOWN/DEGRADED**, not a green 'safe' signal.

Sources:
- https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/dashcamnet
- https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/peoplenet
- https://www.ultralytics.com/license

## 6. Required code hardening — first changes for existing ZIP

1. **P0 / wrong-camera fatigue**: `runtime/systemd/mh02-fatigue.service` and `runtime/mh02_runtime/fatigue_service.py`; remove front HLS default for driver monitoring. Explicit independent camera IDs and source contracts.
2. **P0 / stale fatigue and GNSS**: `aggregate_service.py`, `alert_service.py`, `store.py`, `gps_service.py`; frame timestamp/age/heartbeat/freshness states and tests. Closed eyes from stale samples may NEVER trigger a new event.
3. **P0 / media PTS integrity**: `vlog_service.py`; tie segment time to buffer PTS, not callback wall time. Publish complete only after fragment closed, ffprobe integrity check and durable manifest.
4. **P0 / alert clipping integrity**: `alert_clip_service.py`; actual media boundaries, keyframe seek tolerances, gap/no-data states, stitched segments, clip provenance and hashes.
5. **P0 / camera restart**: camera stable path, no `/dev/video0` dependency, bounded preview/inference queues, non-leaky recording policy, startup/recovery after USB detach and power cycle.
6. **P0 / auth/storage**: secure `web_server.py`/`mediamtx.yml` network paths and recordings/GPS, quotas and pressure handling, priority retention, privacy/data-access policy.
7. **P0 / front inference**: introduce a new NVIDIA-backed front inference service with typed `DetectionEvent` and model manifest rather than modifying the fatigue module to serve both types of camera.
8. **P0 / fleet reproducibility**: idempotent installed package, signed artifacts/manifests, per-unit provisioning/config, exact version lock, canary+rollback and operational telemetry.

The original static audit contains 12 P0 and 12 P1. Locking Orin NX removes the *SKU-unknown* component of P0-10 but **does not close the codec-runtime verification gate**.

## 7. Mass production acceptance gates (draft measurable targets)

- 72h sustained hardware soak in bench configuration, then >=7-day field canary, with **all** features active; no endless RAM growth, repeated crash loops, or unmanaged thermal throttle.
- Front raw segment playback and continuous-coverage accounting from **actual media timeline**, not simplistic sum of file durations. Proposed SLO >=99.5% of available capture time under stable test conditions; all gaps explicitly recorded.
- Cold boot / abrupt ignition power cut / camera hot unplug / network loss / filesystem nearly full / clock jump / recording boundary / exporter restart tested by fault injection. No corrupted segment promoted to `PUBLISHED`.
- Event provenance includes `device_id`, `camera_id`, `boot_id`, `frame_pts`, `capture_utc`, `clock_accuracy`, `model_version`, `confidence`, `gps_age`, `source_recording_hash`, `derived_clip_hash`.
- No stale GPS or stale fatigue trigger, no duplicate events on replay/reboot, and all missing detection states represented as `UNKNOWN`, not `SAFE`.
- Annotated mining dataset: sample multiple operational contexts, road geometry, day/night, dust, rain, backlight, distant person, different DT/SDT, crossing and stationary objects. Set per-class recall/false warning targets with safety stakeholders **before** sign-off.
- Measure recording FPS, inference FPS, end-to-end p50/p95 latency, GPU/CPU/NVENC/NVDEC, RAM, disk IO, temperature and power under all concurrent processes; initial inference p95 <150ms is a **proposed gate, not a verified performance result**.
- Authentication, least privilege for video/GNSS, data retention, audit trail; staged OTA lab -> 1 unit -> small canary -> site rollout with rollback.

## 8. Read-only device inventory before version selection

```bash
cat /etc/nv_tegra_release || true
cat /etc/os-release
cat /proc/device-tree/model 2>/dev/null | tr -d '\0'; echo
dpkg-query -W '*nvidia-l4t*' '*deepstream*' 2>/dev/null
sudo nvpmodel -q
sudo jetson_clocks --show 2>/dev/null || true
for x in nvv4l2decoder nvv4l2h264enc nvstreammux nvinfer nvtracker splitmuxsink; do
  echo "===== $x ====="
  gst-inspect-1.0 "$x" 2>&1 | head -n 16
done
v4l2-ctl --list-devices
find /dev/v4l/by-id -maxdepth 1 -type l -ls 2>/dev/null
lsblk -o NAME,MODEL,SIZE,FSTYPE,MOUNTPOINTS
systemctl --no-pager --type=service --state=running | grep -Ei 'mh02|mediamtx' || true
```

Do not disclose camera credentials, token secrets, RTSP passwords or private IPs in inventory output. `nvpmodel -q` is a read-only query; do not invoke configuration-changing power modes or flash commands until the board image strategy is agreed.

## 9. Decision still required

- Exact **carrier board / cooling & electrical power configuration**.
- Actual **JetPack/L4T + CUDA/TensorRT + GStreamer version** on deployed representative board.
- Exact front/cabin camera **model, USB-vs-RTSP, codec and FPS**, sensor mount/FOV.
- Disk type/capacity/endurance and required raw recording retention (continuous vs event-only for cabin).
- Release management source repo / branch / who owns device provisioning + OTA.
- Safety use case of front detection: **logging-only, operator warning, or safety-critical intervention**. Each has different data and verification requirements.

**Decision status:** Orin NX 16GB hardware target confirmed. Production stack, detector, power mode and performance remain conditional on board inventory and validation. Do not mass deploy existing ZIP based only on syntax success and a single working video.
