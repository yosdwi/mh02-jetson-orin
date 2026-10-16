# Skill: Jetson Video Pipeline Reliability

Use for camera ingest, RTSP/USB, GStreamer/DeepStream, NVMM, encoder and segmented recording changes.

## Workflow
1. Capture exact Jetson Orin NX 16GB board/BSP/JetPack/GStreamer/codec plugins, camera codec/resolution/device UID, nvpmodel and storage. Confirm this is from a real device.
2. Map one physical camera to one owning pipeline, independent front/cabin IDs and branches. Document source timebase/PTS, queue max buffers/time/bytes and policies for preview versus recorder.
3. Start with single source (hardware decode + encode/pass-through when appropriate), ffprobe finalized segments and tegrastats during live client. Next test simultaneous recording + inference and second camera.
4. Instrument fragment-open/fragment-closed, media PTS, gaps, keyframes, encode throughput, EOS/error and watchdog action. Recording lifecycle cannot publish early.
5. Fault inject USB disconnect/reconnect, camera outage, slow browser, disk full, process crash, power cut, thermal overload, clock change.
6. Report measured CPU/RAM/GPU/ENC/DEC/power/temp/dropped frames and 10-minute + 72-hour behavior. Never infer GPU acceleration from plugin names alone.

## Done only when
Reproducible pipeline/config, live proof from target hardware, playable segments, no unbounded RAM/queue, gap/recovery evidence and rollback documented.
