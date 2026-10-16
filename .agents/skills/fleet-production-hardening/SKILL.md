# Skill: Fleet-Scale Jetson Release Hardening

Use for packaging, systemd, security, device provisioning, OTA, local disk and fleet monitoring.

## Workflow
1. Inventory current deployed code/branch, device config, systemd dependency graph, mount points, persistence, storage endurance, power/ignition and thermal envelope.
2. Ensure least privilege, credential injection, per-unit identity, web/media auth, protected RTSP publisher endpoints and no secret in repo/log.
3. Make installs idempotent and version pinned; signed release/manifest, staged canary and tested rollback to last healthy version. Avoid blindly `pip install -U` on devices.
4. Set disk budget / watermark, raw vs pinned-alert retention and upload retry; recover from corrupt power loss, no network, full disk and process restart.
5. Set health signals per source/service: camera, recorder, GPS quality, inference latency/errors, API/auth, storage, temperature, memory and encode/decode loads.
6. Run synthetic local unit tests, Jetson-in-loop validation, 72-hour bench soak and district pilot; report exact pass/fail and release evidence.

## Done only when
Recovery/rollback/redeploy is proven on the target hardware with verifiable privacy, observability, capacity and operator approval.
