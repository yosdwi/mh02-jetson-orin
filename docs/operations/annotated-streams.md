# Device-side annotated streams

MH02 live annotation is rendered on the Jetson by NVIDIA DeepStream. The browser selects a MediaMTX WebRTC path and does not draw detection or fatigue metadata on a Canvas. Clean recording remains owned by `mh02-vlog.service` and `mh02-cabin.service`; inference failures cannot stop those recorder processes.

## Paths

- `/front` is the clean Front publisher.
- `/front-annotated` is published by `mh02-front-inference.service` after `nvinfer`, `nvtracker`, `NvDsDisplayMeta`, `nvdsosd`, and NVIDIA H.264 encoding.
- `/cabin` is the clean Cabin publisher.
- `/cabin-annotated` is published by `mh02-cabin-annotation.service` when a Cabin publisher is provisioned.

The shared `OverlayComposer` supplies device, unit, camera, timestamp, ACC, GPS state, and current GPS values. Coordinates and speed are emitted only for a current `GPS FIX`; `GPS NO SIGNAL`, `GPS DISCONNECTED`, and `GPS UNKNOWN` show unavailable values as `--`. Cabin MediaPipe observations are joined by `(camera_id, stream_epoch, frame_seq)` in a bounded result joiner. PTS is retained only as a local branch bridge to recover that identity, and duplicate, missing, or discontinuous PTS values are diagnosed. Expired or mismatched observations render `FATIGUE AI UNAVAILABLE/DELAYED` and do not get copied to unrelated frames.

## Configuration

`RuntimeConfig.inference` controls Front OSD and its RTSP publisher. `RuntimeConfig.cabin_annotation` controls the Cabin adapter, sampling interval, PTS synchronization budget, OSD layout, and publisher. Configuration changes remain versioned and require the existing controlled service restart path.

## Jetson evidence

On the development Jetson, DeepStream 6.2 user-space plugins and `pyds` were loaded without changing JetPack. Front annotated output was observed online at `/front-annotated` as H.264 1920×1080, with TensorRT running at 24.5 FPS, 122 detections, and zero dropped frames during the validation window. `tegrastats` reported GR3D activity between 8% and 33% during capture. The clean recorder remained active.

The installed device currently has no verified Cabin publisher or `/cabin` stream. The Cabin annotation service is therefore explicitly disabled in the active development configuration and publishes a blocked health artifact; it must not be reported as an operational annotated stream until a second camera source is provisioned and validated.

## Rollback

Restore the pre-OSD Jetson backup under `/home/smartd/mh02_backups/osd-20261017T173715Z`, restore the systemd units and `config.json`, run `systemctl daemon-reload`, then restart only the affected inference, MediaMTX, GPS, aggregate, and web services. Raw recordings and the SQLite state are outside the source rollback path and must be preserved.
