# MH02 runtime

The runtime is split into GPS, aggregate, vlog, fatigue, datalogger, alerts, alert clips, and web processes.

GPS opens the Quectel AT port only long enough to run `AT+QGPS?`. It sends `AT+QGPS=1` only when the modem reports GNSS disabled, then reads NMEA continuously from the stable `ttyUSB1` by-id path. Fixes are checksum-checked and become `NO_FIX` or `STALE` when their observation age exceeds the aggregate freshness budget.

Vlog keeps the front camera stream in Jetson GStreamer. Each segment is a raw ten-minute MP4. The aggregate samples are written to a matching WebVTT metadata track, so the browser can load telemetry without changing the MP4 bytes. A segment is published only after GStreamer can decode it to EOS; an MP4 containing only a `moov` atom is not verified. Cue timing uses media PTS only when every cue sample has PTS; otherwise all cues use UTC observation time and retain fallback uncertainty. Duplicate effective timestamps are coalesced. Live video is published to MediaMTX over RTSP and read by the dashboard with WebRTC; HLS remains a fallback.

Fatigue is cabin-only. Its source must be an explicit `/live/cabin.m3u8` stream and the service will not fall back to the front stream. The current device evidence has a front publisher but no verified cabin publisher or cabin route, so fatigue remains unavailable until that owner is provisioned. Alert events identify the cabin as the detection source and the front recording as road-context evidence; a missing pre/post front interval is recorded as partial evidence rather than complete evidence.

Datalogger consumes the aggregate stream and writes one compressed Parquet file for each completed local hour. The alert service turns sustained closed-eye and yawning signals into pre/on/post events. The alert clip service trims finalized Vlog segments with GStreamer into raw event MP4 plus event-relative VTT. The dashboard exposes finalized MP4 segments as a grid, plays telemetry from VTT as a browser overlay, and lists alerts with direct alert-video, recording, and datalog downloads when evidence is available. Video download links return a ZIP containing the raw MP4, matching VTT sidecar, and optional metadata JSON.

The dashboard also exposes a front/cabin live selector, an isolated fatigue test lab, effective configuration, version history and rollback. Simulation sessions are labeled `SIMULATION`, persisted as bounded test reports, and never enter operational alerts or raw recordings. Live cabin sessions fail closed until a real cabin publisher and capture profile are provisioned. Configuration mutations require `MH02_ADMIN_TOKEN`; restart requests are accepted only for the service allowlist and are never arbitrary shell commands.

The front inference adapter is an optional, disabled-by-default DeepStream 6.2/TensorRT path for the measured JetPack 5.1.1 / L4T R35.3.1 target. It consumes the existing front RTSP publisher or an explicit MP4 replay, then writes versioned detection and advisory warning NDJSON plus an atomic health artifact. It uses `nvinfer` and `nvtracker` when the plugins and an approved TensorRT engine are present; it never fabricates detections and cannot own or stop raw recording. The web workspace shows only observations read from that artifact, including model digest, PTS/source kind, tracking ID and measurable health. A Dashboard `BLOCKED` status is correct until DeepStream plugins, bindings, tracker configuration and license-cleared model assets are commissioned.

Runtime service logs are emitted as JSON to systemd-journald. Install the example journald drop-in as `/etc/systemd/journald.conf.d/mh02.conf` to enable persistent storage and the seven-day development quota. The web diagnostics endpoint provides service status, a 24-hour journal query window and a downloadable diagnostic bundle. This is operational instrumentation, not a substitute for authenticated production API/media access; the roadmap still blocks M3 until that access control is implemented.

The default state paths are:

- `/var/lib/mh02/state/mh02.sqlite3`
- `/var/lib/mh02/recordings/front/*.mp4` and `*.vtt`
- `/var/lib/mh02/recordings/alerts/*.mp4`, `*.vtt`, and `*.json`
- `/var/lib/mh02/datalog/*.parquet`
- `/var/lib/mh02/hls/front.m3u8`
- `/var/lib/mh02/hls/cabin.m3u8`
- `/etc/mh02/smartd.json`

Alert clip metadata includes `evidence_status` (`complete`, `partial`, or `unavailable`), the front recording filenames used, and missing UTC intervals. Raw front recordings are never rewritten or deleted.

Run modules with `PYTHONPATH=/opt/mh02-runtime` and the Jetson virtual environment, or use the systemd units in `systemd/`.

The repository contains `systemd/mh02-cabin.service` and an explicit `cabin` MediaMTX path. It is intentionally guarded by the active configuration and `/dev/v4l/by-id/mh02-cabin`; the current Jetson inventory has only one UVC camera and has not verified a cabin publisher. The unit must be provisioned and tested on the target before cabin integration can be called operational. Front recording remains independent of fatigue or front-object inference.
