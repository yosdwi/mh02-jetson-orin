# Production Release Gates — Orin NX 16GB

**No gate is currently claimed PASSED.** Evidence requires exact device SKU/board/JetPack/power profile, software/model versions, test time, logged metrics and approving engineer. Targets below are initial proposals, not current measurements.

| Gate | Acceptance | Artifact |
|---|---|---|
| G0 Reproducibility | pinned OS/BSP/deps/config schema + build manifest + secrets externalized | signed build ID, SBOM, provisioning rehearsal |
| G1 Correctness | stale fatigue/GPS cannot trigger/claim valid; camera_id and clock epochs correct | deterministic regression/replay report |
| G2 Video | front 1080p30 target under simultaneous inference; no missing coverage hidden; fragment VERIFIED only after finalization | PTS/ffprobe and coverage logs |
| G3 Fault tolerance | USB disconnect, camera EOS, disk full, power loss, reboot, interrupted clip export, offline queue tested | fault-injection matrix and files before/after |
| G4 Security | unauthorized live/archive/GPS denied; secrets out of repo; signed updates and audit trail | route/auth audit and secret scan |
| G5 Storage | configurable quota/retention, priority pinned-alert evidence, watermark alarm, bounded RAM/queues | 72-hour disk/buffer/health graphs |
| G6 Inference | labelled mine domain per-class recall/FP/h and p95 latency, thermal margins and engine versions | dataset version, scoring report, on-device tegrastats |
| G7 Reliability | 72-hour bench soak; 7-day canary pilot; recovery and rollback practiced | graphs, evidence coverage %, gate signoffs |
| G8 Evidence | original hashes + VTT timing validity + derived clip hashes + replay across segment boundaries | integrity manifest and media replay tests |

Suggested initial SLOs **to confirm with operations**: ≥99.5% capture coverage under stable power/camera, event-to-media UTC target ≤250ms if measured, p95 inference latency <150ms at target FPS. No implication that actual hardware meets these.

## Read-only Jetson inventory

```bash
cat /etc/nv_tegra_release || true
cat /etc/os-release
cat /proc/device-tree/model 2>/dev/null | tr -d '\0'; echo
sudo nvpmodel -q
dpkg-query -W '*nvidia-l4t*' '*deepstream*' 2>/dev/null
v4l2-ctl --list-devices
find /dev/v4l/by-id -maxdepth 1 -type l -ls 2>/dev/null
gst-inspect-1.0 nvv4l2decoder
gst-inspect-1.0 nvv4l2h264enc
gst-inspect-1.0 nvinfer
lsblk -o NAME,MODEL,SIZE,ROTA,FSTYPE,MOUNTPOINTS
```

Never copy deployed credentials, video, GPS routes or identity into issue logs. Device access is outside this repository's offline static audit.
