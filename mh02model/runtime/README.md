# MH02 runtime

The runtime is split into GPS, aggregate, vlog, fatigue, datalogger, alerts, alert clips, and web processes.

GPS opens the Quectel AT port only long enough to run `AT+QGPS?`. It sends `AT+QGPS=1` only when the modem reports GNSS disabled, then reads NMEA continuously from the stable `ttyUSB1` by-id path. Fixes are checksum-checked and become `NO_FIX` or `STALE` when their observation age exceeds the aggregate freshness budget.

Vlog keeps the front camera stream in Jetson GStreamer. Each segment is a raw ten-minute MP4. The aggregate samples are written to a matching WebVTT metadata track, so the browser can load telemetry without changing the MP4 bytes. A segment is published only after GStreamer can decode it to EOS; an MP4 containing only a `moov` atom is not verified. Cue timing uses media PTS only when every cue sample has PTS; otherwise all cues use UTC observation time and retain fallback uncertainty. Duplicate effective timestamps are coalesced. Live video is published to MediaMTX over RTSP and read by the dashboard with WebRTC; HLS remains a fallback.

Fatigue is cabin-only. Its source must be an explicit `/live/cabin.m3u8` stream and the service will not fall back to the front stream. The current device evidence has a front publisher but no verified cabin publisher or cabin route, so fatigue remains unavailable until that owner is provisioned. Alert events identify the cabin as the detection source and the front recording as road-context evidence; a missing pre/post front interval is recorded as partial evidence rather than complete evidence.

Datalogger consumes the aggregate stream and writes one compressed Parquet file for each completed local hour. The alert service turns sustained closed-eye and yawning signals into pre/on/post events. The alert clip service trims finalized Vlog segments with GStreamer into raw event MP4 plus event-relative VTT. The dashboard exposes finalized MP4 segments as a grid, plays telemetry from VTT as a browser overlay, and lists alerts with direct alert-video, recording, and datalog downloads when evidence is available. Video download links return a ZIP containing the raw MP4, matching VTT sidecar, and optional metadata JSON.

The default state paths are:

- `/var/lib/mh02/state/mh02.sqlite3`
- `/var/lib/mh02/recordings/front/*.mp4` and `*.vtt`
- `/var/lib/mh02/recordings/alerts/*.mp4`, `*.vtt`, and `*.json`
- `/var/lib/mh02/datalog/*.parquet`
- `/var/lib/mh02/hls/front.m3u8`
- `/etc/mh02/smartd.json`

Alert clip metadata includes `evidence_status` (`complete`, `partial`, or `unavailable`), the front recording filenames used, and missing UTC intervals. Raw front recordings are never rewritten or deleted.

Run modules with `PYTHONPATH=/opt/mh02-runtime` and the Jetson virtual environment, or use the systemd units in `systemd/`.
