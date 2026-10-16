# Agent Working Agreement — MH02 Jetson Orin NX 16GB

Applies to the entire repository. **Read this file before planning, editing, testing, reviewing or deploying.** User goals: production-grade fleet edge for **front vlog**, **front pedestrian/vehicle detection**, **separate cabin fatigue**, and trustworthy event evidence.

## 0. Source of truth and prohibited assumptions

- Inspect current Git branch/HEAD, `README.md`, the deployed systemd units, config wiring, relevant modules, and recent PRs before code edits. Never assume prior ZIP/audit is current deployed truth.
- The 2026-10-17 audit and NX addendum are *static evidence and proposals*, not implementation certificates. Document uncertainty instead of inventing JetPack versions, frame rates, model accuracy or measured thermal/load performance.
- Hardware is **Jetson Orin NX 16GB**. Record actual JetPack/L4T, carrier board/BSP, encoder elements, USB camera IDs, power mode and storage before choosing versions or making GPU claims. Do not silently upgrade OS, CUDA, DeepStream or dependencies.
- Do not modify running edge units, upload real footage, or publish private credentials without explicit deployment authorization.

## 1. Architecture / clean-code boundaries

- **One ingest owner per physical camera.** Front and cabin are distinct camera IDs, configuration, signal quality and lifecycles. No accidental `front` fallback for fatigue.
- Split modules by responsibility: camera ingest/recording; inference adapters; event/rule engine; GPS/time synchronization; evidence/provenance; storage; API; fleet lifecycle. No giant application class owning everything.
- Keep business policies independent of transport, framework, OpenCV frames or GStreamer buffers. Use typed versioned data contracts, explicit units and UTC timestamps.
- Canonical event includes `event_id`, `boot_id`, `camera_id`, `frame_id`, media `pts`, observed UTC with uncertainty, source freshness, model/rule version, classification confidence, GPS quality, lifecycle and provenance. Never infer precision from wall time.
- Dependency direction: runtime adapters → interfaces/domain; domain cannot import camera/web/DB implementations. Avoid cyclic imports and duplicated GPS readers.
- DRY without abstraction inflation; small functions with single responsibility; meaningful names; typed interfaces; explicit configuration validation; documented failure semantics. Prefer smallest reversible change instead of broad rewrite.

## 2. Recording/evidence correctness, fail-safe operation

- **Raw footage is immutable.** Generate VTT and human-readable overlay MP4 as derived artifacts, retaining original hashes, input segment IDs, renderer/model/software version, and actual media timing.
- Recording must survive inference failure. Prioritize recording and alert retention under backpressure; bounded queues for preview/inference, explicit recording pressure handling and gaps. Never silently drop frames and report complete.
- Segment lifecycle `OPEN → FINALIZING → VERIFIED → PUBLISHED`, publish after fragment close and validation. Crash/disk-full/restart states must be deterministic and observable.
- Stale/invalid GPS or detector outputs become `UNKNOWN/STALE` and may **not** trigger new alerts. Clock correlation must use media PTS + monotonic/UTC mapping and report timing uncertainty.
- Alert clips spanning boundaries must verify actual timestamp/PTS, gaps and complete post-event availability; do not claim frame accuracy based on keyframe seek alone.
- Model *detection* does not automatically imply collision risk. Rules require domain-specific calibration/validation and safety review.

## 3. Jetson GPU / camera / model policy

- GStreamer/NVIDIA codecs are the camera-video foundation. DeepStream + TensorRT are first candidates for multi-camera front inference. Measure actual decode/encode engine use, copies (NVMM), CPU, RAM, thermal and device power on target hardware.
- Do not claim Python MediaPipe GPU if it is using XNNPACK CPU. Do not label OpenVINO `GPU` as Jetson GPU without proven backend. Do not claim NVENC/DeepStream compatibility on another SKU/version.
- Evaluate NVIDIA DashCamNet vs license-approved small YOLO TensorRT FP16 on annotated mine-footage (day/night/IR, dust, rain, vibration, DT/SDT, pedestrian occlusion). Compare per-class recall, FP/h, p95 event latency, CPU/GPU/RAM and thermal **while vlog and cabin run simultaneously**.
- Review model weights/dataset provenance and inference library licensing before redistribution. No unreviewed model download in startup scripts.

## 4. Privacy, security, configuration

- Public GitHub repository: **never commit camera credentials, site IPs tied to deployed infrastructure, device ID/NIK/driver metadata, footage, access tokens, GNSS traces, Redis DB dumps, proprietary binary model weights or secrets**. Use `.example` configs and protected device-secret injection.
- Default deny for web/API/media. Require authenticated live/video/GPS access, authorization and access audit. No wildcard publishing/anonymous browse in production.
- Use least-privilege systemd services; explicit file ownership, log rotation, safe disk thresholds, retention and purge evidence policy.

## 5. Test-driven development and release gates

- Before edits: reproduce observable bug and add an automated regression test whenever possible. Submit source-file/line evidence and state expected/actual behavior.
- After edits: run syntax/type/lint checks applicable to touched files, focused unit tests, integration replay and security/secret scans. Prefer deterministic synthetic frame/metadata fixtures; no production video needed for CI.
- Never equate syntax pass, dry-run pipeline, or mocked inference with Jetson hardware success. Hardware changes require read-only device inventory, tegrastats, GStreamer element checks, media probe, logs and fault-injection evidence.
- Required gates: stale signal safety, recording continuity/recovery, disk-full handling, security, 72-hour soak, field canary, model validation, signed release/rollback; see `docs/operations/release-gates.md`.

## 6. Change control / agent conduct

- **Audit → plan → scoped patch → test → evidence → PR.** Label changes KEEP / REWORK / EXTRACT / DEPRECATE / SHARED; explain regressions and backward compatibility.
- Protect existing functional paths and migration adapters; no redesign-by-default, speculative package swaps or unrelated formatting churn.
- No silent schema breaking. Version events/configs and plan migrations/rollback. Keep unrelated developer changes untouched. Never force-push or rewrite history.
- Every PR summary must include changed services, risk severity, what ran locally versus on Jetson, measurements, known remaining gaps, and rollback procedure.
- Default to English for code/docs identifiers and descriptive commit messages; user-facing documentation may use Bahasa Indonesia.

## Relevant task skills

Use only skills applicable to task; read their `SKILL.md` before implementation:
- `.agents/skills/jetson-video-pipeline/SKILL.md`
- `.agents/skills/edge-evidence-integrity/SKILL.md`
- `.agents/skills/nvidia-inference-benchmark/SKILL.md`
- `.agents/skills/fleet-production-hardening/SKILL.md`

Repository skills are process guidelines, not installed tool permissions. If a skill depends on commands or hardware unavailable to the agent, record the blocked check instead of claiming it passed.
