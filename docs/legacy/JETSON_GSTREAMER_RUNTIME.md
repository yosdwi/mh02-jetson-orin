# Jetson GStreamer runtime

This is the Stage B adapter from `JETSON_IMPLEMENTATION_STRATEGY.md`. It keeps
the legacy MH02 Python processors unchanged while proving USB camera ingest,
Jetson hardware decode/encode, RTSP output, bounded queues, and an optional
recording branch.

The runtime deliberately does not fall back to software decode or encode. A
successful run must use these target elements:

```text
v4l2src -> image/jpeg -> jpegparse -> nvv4l2decoder(mjpeg=1)
         -> nvvidconv/NVMM -> nvv4l2h264enc -> rtph264pay -> GstRtspServer
```

## Run on Jetson

From the MH02 application directory:

```bash
cd /home/smartd/jetson_poc
python3 jetson_gstreamer_runtime.py \
  --camera-id front \
  --device /dev/video0 \
  --width 1920 --height 1080 --framerate 30 \
  --mount /front
```

The USB mode is the default. Use stable `/dev/v4l/by-id/...` paths when more
than one UVC camera is connected. `/dev/video1` on the current Jetson is a
non-capture node for the same physical camera and must not be used as a second
camera. The current camera advertises MJPEG 1920x1080@30 and YUY2 modes.

The output is:

```text
rtsp://<jetson-ip>:8554/front
```

Use a separate client to activate and inspect the shared RTSP media factory:

```bash
gst-launch-1.0 -v rtspsrc location=rtsp://127.0.0.1:8554/front latency=200 \
  ! rtph264depay ! h264parse ! fakesink sync=false
```

For segmented vlog output, add a recording directory. The recording branch is
fed from the same encoded stream as RTSP and rotates files at the requested
duration:

```bash
python3 jetson_gstreamer_runtime.py \
  --camera-id front \
  --device /dev/video0 \
  --mount /front \
  --record-dir /home/smartd/jetson-vlog/front \
  --segment-seconds 60
```

The first version does not attach GPS sidecars yet; that belongs to the vlog
stage after the live streaming path is stable. GPS remains a separate USB
serial/Redis concern: the current Jetson exposes a Quectel EC25 modem on
`/dev/ttyUSB0` through `/dev/ttyUSB3`, and no `gpsd` service is active. The
video runtime does not open those serial ports, so it cannot claim GPS
correlation until the existing GPS bridge or a dedicated NMEA/Quectel reader is
identified.

RTSP input remains available for compatibility with existing deployments:

```bash
python3 jetson_gstreamer_runtime.py \
  --camera-id front \
  --source rtsp \
  --input-url 'rtsp://user:password@camera/stream' \
  --mount /front
```

## Local checks before deployment

These checks do not need GStreamer or Jetson libraries:

```bash
python3 jetson_gstreamer_runtime.py \
  --camera-id front \
  --device /dev/video0 \
  --dry-run --print-pipeline
python3 -m py_compile jetson_gstreamer_runtime.py
```

On the Jetson, use `--check-elements` before starting the server. Capture
`tegrastats` while an RTSP client is connected. The result should identify the
exact decoder/encoder elements, the RTSP URL, the workload interval, CPU/RAM,
and codec accelerator fields. This validates codec acceleration; it does not
yet prove MediaPipe GPU inference.
