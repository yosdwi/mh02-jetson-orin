# Jetson Orin MH02 Implementation Strategy

Status: draft for technical audit

Scope: migration of the existing MH02 camera/GPS application toward a low-CPU, NVIDIA-accelerated video system on Jetson Orin.

## Executive conclusion

The existing system is a useful business-logic baseline, but it is not yet a suitable GPU-video foundation.

The GPS path can be retained. The camera ingest and frame-processing path should be migrated progressively to GStreamer/DeepStream. The existing Python/OpenCV processors should remain as a compatibility path while the GPU path is proven and the detector logic is migrated.

The three requested targets should be implemented in this order:

1. Real-time streaming from front and cabin cameras.
2. Vlog recording from the same live pipeline.
3. Cabin detection and event processing on the GPU pipeline.

The first target is the foundation for the other two. It establishes camera ingest, hardware decode, buffer ownership, RTSP output, timestamps, GPS correlation, telemetry, and reconnection behavior.

## Existing system assessment

### Existing strengths

- GPS data is already consumed through Redis.
- The application already parses timestamp, speed, latitude, longitude, status, and heartbeat data.
- Front and cabin cameras already have RTSP configuration.
- Existing visualizers, alert logic, deviation logic, and event recording contain valuable business behavior.
- Existing configuration files define camera URLs, frame sizes, detection modes, recording settings, and network ports.

Relevant entry points:

- [mh02_front.py](mh02model/apps/mh02/mh02_front.py)
- [mh02_cabin_old.py](mh02model/apps/mh02/mh02_cabin_old.py)
- [CameraCV2.py](mh02model/apps/mh02/classes/CameraCV2.py)
- [RedisManager.py](mh02model/apps/mh02/classes/RedisManager.py)
- [ProcessorCabinBehavior.py](mh02model/apps/mh02/classes/ProcessorCabinBehavior.py)
- [CollisionDetector.py](mh02model/apps/mh02/detectors/CollisionDetector.py)

### Current risks and blockers

1. `CameraCV2` opens RTSP through `cv2.VideoCapture(..., cv2.CAP_FFMPEG)` and returns OpenCV/NumPy frames. This is convenient, but it does not prove Jetson hardware decode or zero-copy operation.
2. Cabin frames are copied into deques and copied again before processing. This creates CPU and RAM pressure.
3. MediaPipe is imported from Python in the cabin processors. The previous Jetson test used the CPU XNNPACK delegate. Requesting the Python GPU delegate failed with `GPU processing is disabled in build flags`.
4. TensorFlow GPU configuration in `mh02_cabin_old.py` does not automatically make MediaPipe use the NVIDIA GPU.
5. The front path uses an imported `Camera` abstraction whose implementation must be verified on the Jetson. The local workspace listing does not currently show a matching `classes/Camera.py` file.
6. Several application paths use Windows-style configuration locations such as `D:\smartd\...`. These must be replaced or parameterized for Linux deployment.
7. `CollisionDetector.py` still uses the legacy OpenVINO Inference Engine API with `device_name="GPU"`. This should not be assumed to mean NVIDIA Jetson GPU execution.
8. GUI calls such as `cv2.imshow` are unsuitable for a headless SSH runtime and should not be part of the production pipeline.
9. Existing event recorders use OpenCV `VideoWriter`. This is not the preferred path for Jetson hardware-encoded vlog output.

## Target architecture

```text
Redis GPS service
    │
    └── latest GPS snapshot
          timestamp, speed, latitude, longitude, heartbeat

GStreamer / DeepStream video runtime
    ├── Front RTSP source
    ├── Cabin RTSP source
    ├── Jetson hardware decode
    ├── NVMM/EGL GPU buffers
    ├── GPU preprocessing
    ├── MediaPipe native GPU or TensorRT inference
    ├── GPU/VIC overlay where applicable
    ├── Jetson hardware encode
    ├── RTSP output
    └── Vlog recording branch
            │
            └── Detection/event metadata
                camera_id, timestamp, GPS snapshot,
                detection type, confidence, geometry
```

The important separation is:

- Video frames remain in the GPU/NVMM/EGL path as long as possible.
- GPS remains a lightweight CPU/Redis service.
- Inference produces metadata and events.
- Business logic consumes metadata instead of requiring every subsystem to receive a copied full-resolution frame.

The intended live video shape is:

```text
RTSP source
  -> rtspsrc
  -> RTP depayloader
  -> H.264/H.265 parser
  -> nvv4l2decoder
  -> NVMM/EGL buffer
  -> GPU inference or preprocessing
  -> nvv4l2h264enc/nvv4l2h265enc
  -> RTP payloader
  -> RTSP server
```

Use GStreamer as the pipeline engine. Use DeepStream when multi-camera batching, inference metadata, recording, or NVIDIA plugins become central to the runtime. Use FFmpeg only for offline conversion, trimming, or auxiliary evidence generation.

## Target 1: real-time front and cabin streaming

This is the first implementation milestone.

### Objective

Receive front and cabin camera streams, decode using Jetson hardware, publish stable RTSP outputs, and demonstrate low CPU usage with telemetry.

### Initial implementation approach

Start with one camera and one pipeline. Prove the complete path before adding the second camera. The first pipeline should not yet include all legacy detection logic.

Required capabilities:

- RTSP source connection and reconnection.
- Hardware decode using the Jetson GStreamer plugin.
- Explicit caps and memory ownership checks.
- Hardware encode for the output stream.
- RTSP server or publishing endpoint.
- Bounded queues and backpressure behavior.
- `tegrastats` capture during idle and running states.

After one camera passes, add the second camera. Initially, separate pipelines may be easier to debug than immediate batching. DeepStream `nvstreammux` can be evaluated after both individual paths are stable.

### GPS integration

Keep the existing Redis GPS service. Do not create a second GPS reader for each camera.

Introduce a clear runtime contract:

```text
GpsSnapshot:
  timestamp
  speed
  latitude
  longitude
  status
  heartbeat
```

Each video event should carry:

```text
VideoEvent:
  camera_id
  frame_timestamp_or_pts
  gps_snapshot
  event_type
  confidence
  geometry_or_landmarks
```

The GPS data does not need GPU acceleration. Its CPU cost is small compared with video decode, inference, and frame conversion.

## Target 2: vlog

Vlog should be a branch of the existing live pipeline, not a second camera reader.

```text
GPU decoded frame
       │
       ├── inference and RTSP output
       │
       └── hardware encode -> segmented MP4/vlog
```

This avoids:

- opening the same RTSP camera multiple times;
- decoding the same frame twice;
- using `cv2.VideoWriter` as the primary encoder;
- storing large numbers of full-resolution NumPy frames in RAM.

For continuous vlog recording, use segmented files with bounded duration and storage policy. For event recording, use a ring buffer or a smart-recording mechanism that preserves pre-event and post-event video.

GPS can be associated with vlog files using a sidecar JSON/CSV event log or a defined timestamp metadata format. The first version should prioritize reliable timestamps and recoverable files over embedding complex metadata into the video container.

## Target 3: cabin functionality

The cabin feature should be migrated after the streaming spine is stable.

The current processing shape is effectively:

```text
OpenCV/NumPy frame
  -> Python MediaPipe/detector
  -> CPU visualizer and business logic
```

The target shape is:

```text
GPU frame
  -> native MediaPipe GPU or TensorRT
  -> detection/landmark metadata
  -> cabin business logic
  -> GPU overlay and event output
```

The valid MediaPipe GPU routes are:

1. Build native MediaPipe with GPU/EGL support on the exact JetPack image.
2. Create a native bridge or custom GStreamer plugin that converts the native GPU buffer to the MediaPipe GPU input without copying every frame to CPU.

If the native MediaPipe route remains blocked, use TensorRT/DeepStream for the cabin model and document MediaPipe as a separate compatibility or research path. Do not silently use the CPU Python wheel while reporting the result as GPU inference.

Legacy cabin business rules can be migrated incrementally. For example, fatigue counters, mask status, alert state, and GPS-linked event records can consume structured detector output without requiring the old camera class to remain in the main video path.

## Migration strategy

Do not rewrite the entire application in one change. Use an adapter boundary:

```text
Existing Redis/GPS and business logic
              │
              ▼
      Stable event contract
              ▲
              │
New GStreamer/DeepStream runtime

## Accepted first implementation contract

The first deployable slice is intentionally split into eight cooperating services
and uses one USB camera. The existing `mh02model` remains the source of the
fatigue detector behavior while the new runtime owns service boundaries,
timestamps, storage, and the web surface.

### Service boundaries

1. **GPS service**
   - Reads the Quectel EC25 GPS/NMEA port exposed by ModemManager as `ttyUSB1`.
   - Uses the stable `/dev/serial/by-id/...if01-port0` path when available.
   - Checks the EC25 AT state on the second AT port (`ttyUSB3`) and sends
     `AT+QGPS=1` only when `AT+QGPS?` reports GNSS disabled.
   - Publishes the latest typed GPS snapshot; it is the only process allowed to
     read the GPS serial stream.

2. **Aggregate service**
   - Reads the existing Redis payload when present and combines it with the GPS
     snapshot.
   - Adds a local wall-clock timestamp, monotonic timestamp, `device_id`, and
     `unit_no`.
   - Persists the latest payload and a timestamped sample stream in the runtime
     state database. Video, fatigue, and web services consume this contract
     instead of reading Redis or the serial port independently.

3. **Vlog service**
   - Starts with one UVC camera (`/dev/video0`) through the proven Jetson
     GStreamer hardware decode/encode path.
   - Writes raw segmented MP4 files with a ten-minute target duration.
   - Does not burn aggregate data into the pixels. Each segment has a matching
     WebVTT sidecar (`.vtt`) whose cues are generated from the same monotonic
     timeline as the MP4 segment.

4. **Fatigue service**
   - Reuses the existing `mh02model` cabin detector contract for `CLOSEDEYES`
     and `YAWNING`.
   - Initially runs as a compatibility CPU path against sampled frames so the
     business behavior is verified before a native GPU bridge is attempted.
   - Emits fatigue events into the aggregate/event store; it does not modify the
     raw MP4.

5. **Datalogger service**
   - Consumes the aggregate sample stream at one sample per second.
   - Buffers samples by the Jetson's local hour and atomically writes completed
     hours as compressed Parquet files under `/var/lib/mh02/datalog`.
   - Exposes only completed files for download, with row counts and hour metadata.

6. **Alert service**
   - Consumes the aggregate fatigue flags and turns a continuous `closed_eyes` or
     `yawning` signal into a persisted lifecycle event after two seconds.
   - Stores pre-event context (7.5 seconds), the detected on-duration, and a
     post-event window (4.5 seconds) in SQLite so every alert can be reviewed.
   - Links each alert to overlapping finalized recordings and hourly datalogs in
     the web API.

7. **Web service**
   - Exposes the latest aggregate payload as JSON.
   - Binds the dashboard to `0.0.0.0:8080` for access from another computer.
   - Publishes the live camera through MediaMTX: GStreamer sends local RTSP,
     browsers read WebRTC/WHEP on port `8889`, and HLS remains the fallback.
   - Shows a 24-hour coverage bar: green means recording and datalog are complete,
     orange means one is incomplete, and red means both are missing/incomplete.
   - Shows finalized recordings as compact grid cards. Selecting a card opens one
     archive player and loads the matching WebVTT sidecar at playback time rather
     than encoding telemetry into pixels.
   - Lists fatigue alerts with their pre/on/post window, recording count, and a
     direct alert-video, recording, and datalog download when available. Video
     downloads are ZIP bundles containing the raw MP4, its matching WebVTT
     sidecar, and the optional metadata JSON. Opening an alert selects the
     related recording and seeks to the evidence start; alerts without an
     overlapping finalized segment are marked as video unavailable.
   - Lists completed hourly Parquet datalogs below the recordings for download.

8. **Alert clip service**
   - Waits until an alert's post window and overlapping Vlog segments are
     finalized before exporting evidence.
   - Trims the raw H.264 stream with GStreamer, joins a boundary-spanning event
     through a transport-stream remux, and writes `alert-*.mp4` without burned-in
     telemetry.
   - Writes a matching event-relative WebVTT file and updates the alert record so
     the dashboard can play or download the alert clip directly.

### Timestamp and sidecar contract

The aggregate sample is the synchronization source:

```text
AggregateSample:
  sequence
  timestamp_utc
  monotonic_ns
  device_id
  unit_no
  gps_snapshot
  redis_payload
  fatigue
```

For each MP4 segment, the vlog service stores `segment_start_monotonic_ns` and
maps aggregate samples to relative WebVTT cue times. Each cue contains three
human-readable lines matching the dashcam overlay: NMEA GPS and speed, device
and unit identity, then local date/time and camera channel. The MP4 remains raw
and independently recoverable if the sidecar is missing.

### Initial storage layout

```text
/var/lib/mh02/
  state/mh02.sqlite3
  recordings/front/front-YYYYMMDD-HHMMSS.mp4
  recordings/front/front-YYYYMMDD-HHMMSS.vtt
  recordings/front/front-YYYYMMDD-HHMMSS.json
  recordings/alerts/alert-<event-id>.mp4
  recordings/alerts/alert-<event-id>.vtt
  recordings/alerts/alert-<event-id>.json
  datalog/datalog-YYYYMMDD-HH.parquet
  datalog/datalog-YYYYMMDD-HH.parquet.json
  alert_events (SQLite table)
  snapshots/latest-aggregate.json
```

The first milestone is complete when the Jetson can run the GPS, aggregate, and
datalogger services, record one USB camera into ten-minute finalized MP4/VTT
pairs, expose latest aggregate data through HTTP, and show the coverage bar plus
single-player archive. GPU inference remains
a separately measured milestone; the existing Python MediaPipe wheel must not be
reported as GPU-backed.
```

Recommended migration stages:

### Stage A: inventory and baseline

- Verify JetPack/L4T, CUDA, GStreamer plugins, camera URLs, Redis availability, power mode, and clocks.
- Record the current CPU/RAM/GPU behavior.
- Identify Linux path/configuration issues.
- Confirm the exact front and cabin camera codecs and resolutions.

### Stage B: one-camera hardware pipeline

- Implement one RTSP input using GStreamer.
- Verify `nvv4l2decoder`, NVMM/EGL caps, and hardware encode.
- Publish a test RTSP output.
- Capture telemetry and a short evidence stream.

### Stage C: two-camera streaming

- Add the second camera.
- Define camera IDs and timestamps.
- Add reconnect handling and bounded queues.
- Confirm RAM does not grow under continuous operation.

### Stage D: vlog branch

- Add hardware-encoded segmented recording.
- Add GPS sidecar metadata.
- Test disk rotation and recovery after restart.

### Stage E: GPU inference

- Prove native MediaPipe GPU initialization independently.
- Bridge one camera to the GPU inference path.
- Confirm inference workload overlaps with nonzero `GR3D_FREQ`.
- Add metadata and event output.

### Stage F: cabin/business migration

- Move cabin rules from full-frame coupling to structured detection metadata.
- Add GPU overlay only where required.
- Retire the CPU-heavy camera path after feature parity and telemetry comparison.

## GPU and CPU acceptance criteria

The implementation should not be accepted merely because an MP4 file is produced.

### Streaming acceptance

- Front stream is received and published.
- Cabin stream is received and published.
- Reconnect works without unbounded RAM growth.
- Hardware decode and encode elements are present and active.
- CPU is measured and remains bounded under the target resolution/FPS.

### MediaPipe GPU acceptance

- Runtime log proves native GPU/EGL initialization or an explicit GPU delegate.
- The GPU inference workload is active during the telemetry interval.
- `GR3D_FREQ` responds during the inference workload, or an equivalent accelerator metric is documented.
- No unmeasured `appsink -> OpenCV -> NumPy` copy is presented as a full GPU path.
- The result includes BEFORE, RUNNING, and AFTER telemetry.

### Vlog acceptance

- Recording uses the same live pipeline branch.
- Encoding uses Jetson hardware where supported.
- Segment rotation and storage limits are defined.
- GPS correlation is present and timestamped.

### Cabin acceptance

- Existing cabin event semantics are preserved or explicitly mapped.
- Alert and event outputs remain compatible with the existing consumers.
- CPU and RAM are compared against the current implementation.
- GPU and codec telemetry is captured during the same workload.

## Telemetry interpretation

CPU cannot be literally zero. Network receive, scheduling, queues, timestamps, and application control still require CPU. The target is low and stable CPU usage, not the absence of all CPU activity.

For interpretation:

- `GR3D_FREQ` is the important signal for MediaPipe GPU/3D inference.
- Hardware decode/encode may use NVDEC/NVENC/VIC and may not significantly raise `GR3D_FREQ`.
- `EMC_FREQ` indicates memory-controller activity, not proof of inference.
- RAM growth should be checked for queue retention, frame copies, batching, and recording buffers.

## Key technical decisions

| Area | Decision |
|---|---|
| Live video pipeline | GStreamer |
| Multi-camera/inference pipeline | DeepStream on GStreamer |
| Offline video tools | FFmpeg |
| Native NVIDIA inference | TensorRT/DeepStream |
| MediaPipe GPU | Native C++ MediaPipe with GPU/EGL bridge |
| GPS | Keep Redis/CPU service |
| Vlog | Pipeline branch with hardware encoder |
| Legacy logic | Preserve behind an adapter during migration |
| OpenVINO | Do not make it the Jetson GPU foundation without backend proof |

## Audit questions for the next agent

1. Is the exact JetPack/L4T version confirmed on the target Jetson?
2. Which front and cabin codecs are actually delivered by the cameras?
3. Do the installed GStreamer plugins include the required NVIDIA decoder and encoder?
4. Does the camera pipeline preserve NVMM/EGL memory until the inference boundary?
5. Is MediaPipe native GPU initialization successful on this exact image?
6. Does the inference interval correlate with nonzero `GR3D_FREQ`?
7. Is the CPU frame-copy boundary explicitly measured or eliminated?
8. Can GPS timestamps be correlated with video PTS and event timestamps?
9. Can vlog recording operate as a branch of the same pipeline?
10. Are all Linux configuration paths and runtime secrets externalized?

## References

- [NVIDIA Accelerated GStreamer for Jetson](https://docs.nvidia.com/jetson/archives/r35.3.1/DeveloperGuide/text/SD/Multimedia/AcceleratedGstreamer.html)
- [NVIDIA DeepStream Overview](https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_Overview.html)
- [GStreamer hardware-accelerated video decoding](https://gstreamer.freedesktop.org/documentation/tutorials/playback/hardware-accelerated-video-decoding.html)
- [FFmpeg documentation](https://ffmpeg.org/ffmpeg-all.html)
