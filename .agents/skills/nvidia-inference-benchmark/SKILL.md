# Skill: NVIDIA Native Front Detection Benchmark

Use for selecting/training/exporting pedestrian and vehicle detection models on Orin NX 16GB.

## Workflow
1. Define mine operational classes (person, light vehicle, DT/SDT, motorcycle), ROI, distance/risk interpretation and human-validated labels; avoid confusing detector with warning logic.
2. Prepare train/val/test split by route, shift, camera unit and conditions: dusk/night/IR, dust, rain, glare, occlusion, vibration. Keep private footage outside GitHub.
3. Candidate reference models: NVIDIA DashCamNet, PeopleNet+TrafficCamNet, licensing-approved small YOLO TensorRT FP16; check class mapping, inference preprocessing and license redistribution.
4. Verify exports against reference model outputs, confidence/NMS consistency, versioned engine build and exact DeepStream/JetPack support.
5. Benchmark on **real Orin NX** with 1080p vlog, live preview and cabin detector running; collect recall/precision, false alerts per hour, p50/p95 latency, dropped-frame rates, thermal/power/CPU/GPU/RAM.
6. Optimize only after correctness. INT8 requires representative calibration, class-by-class accuracy regression and deployment rollback plan.

## Done only when
Documented dataset/model/license/engine version, reproducible commands, acceptance thresholds approved by domain owner and same-workload on-device results.
