# MH02 runtime

The runtime is split into GPS, aggregate, vlog, fatigue, datalogger, alerts, alert clips, and web processes.

GPS opens the Quectel AT port only long enough to run `AT+QGPS?`. It sends `AT+QGPS=1` only when the modem reports GNSS disabled, then reads NMEA continuously from the stable `ttyUSB1` by-id path.

Vlog keeps the camera stream in Jetson GStreamer. Each segment is a raw ten-minute MP4. The aggregate samples are written to a matching WebVTT metadata track, so the browser can load telemetry without changing the MP4 bytes. Live video is published to MediaMTX over RTSP and read by the dashboard with WebRTC; HLS remains a fallback.

Datalogger consumes the aggregate stream and writes one compressed Parquet file for each completed local hour. The alert service turns sustained closed-eye and yawning signals into pre/on/post events. The alert clip service trims finalized Vlog segments with GStreamer into raw event MP4 plus event-relative VTT. The dashboard exposes finalized MP4 segments as a grid, plays telemetry from VTT as a browser overlay, and lists alerts with direct alert-video, recording, and datalog downloads when evidence is available. Video download links return a ZIP containing the raw MP4, matching VTT sidecar, and optional metadata JSON.

The default state paths are:

- `/var/lib/mh02/state/mh02.sqlite3`
- `/var/lib/mh02/recordings/front/*.mp4` and `*.vtt`
- `/var/lib/mh02/recordings/alerts/*.mp4`, `*.vtt`, and `*.json`
- `/var/lib/mh02/datalog/*.parquet`
- `/var/lib/mh02/hls/front.m3u8`
- `/etc/mh02/smartd.json`

Run modules with `PYTHONPATH=/opt/mh02-runtime` and the Jetson virtual environment, or use the systemd units in `systemd/`.
