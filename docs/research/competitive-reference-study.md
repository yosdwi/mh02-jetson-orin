# Reference Product Study — MH02 Industrial Edge Safety

**Status:** research baseline; NOT a verification of competitor internals, certifications or measured safety effectiveness.  
**Date:** 2026-10-17  
**Scope:** Jetson Orin NX 16GB, front continuous vlog, front pedestrian/vehicle detection, cabin fatigue, alert evidence, local-first operations, fleet deployment.

## The product category we are building

MH02 is a combination of (a) video telematics/dashcam, (b) industrial pedestrian/vehicle awareness, and (c) mining driver monitoring. No single reference below is assumed to supply every MH02 requirement or run on Jetson.

| Reference | Demonstrated/published focus | ADOPT as design principle | Do **not** infer |
|---|---|---|---|
| Blaxtair Origin | industrial pedestrian proximity detection, danger alerts, avoidance of unnecessary alarms | hazard-zone UX, posture/occlusion test scenarios, alert relevance and operator human factors | proprietary model, numerical performance, suitability with one front camera |
| Hexagon Operator Alertness System | fatigue/distraction detection, alerting and reporting in mining vehicles | cabin DMS lifecycle, intervention escalation, event review | identical eye/yawn thresholds, engine internals, certified performance |
| Netradyne Driver•i | road-/driver-facing video analytics, telematics and event review | synchronized dual-camera concept, searchable evidence timeline, fleet UX | mining capability equivalence, GPS accuracy guarantees, same cost/performance |
| Cat MineStar Detect | mining equipment/driver safety system portfolio; camera/radar sensing in some variants | investigate complementary sensors and operator alert ergonomics | camera-only depth accuracy or collision avoidance certification |
| NVIDIA DeepStream Smart Video Record | event video cache parallel to inference; encoded-frame recording | event pre/post buffer separated from expensive inference, reproducible media manifests | precise pre-event duration without keyframe/PTS tests |
| NVIDIA DashCamNet | four-class detection: car, person, road sign, bicycle/two-wheeler | NVIDIA-native moving-camera baseline candidate | DT/SDT classes, collision risk, night/mine-domain recall or automatic redistribution permission |

### Primary references

- Blaxtair Origin operator/product documentation: https://doc.blaxtair.com/en/bxto/Working-version/system-presentation
- Hexagon Operator Alertness System: https://hexagon.com/products/hexagon-operator-alertness-system
- Netradyne Driver•i: https://www.netradyne.com/products/fleet-camera-system
- Cat MineStar Detect: https://www.cat.com/en_US/by-industry/mining/surface-mining/surface-technology/detect1.html
- DeepStream smart video recording: https://docs.nvidia.com/metropolis/deepstream/9.1/text/DS_Smart_video.html
- NVIDIA DashCamNet model card: https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/dashcamnet
- NVIDIA model limitations: https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/dashcamnet/-/model-card/explainability

*Evidence discipline:* vendor pages document advertised capabilities, not externally reproduced benchmarks. Their visuals, footage, models and source code are not permission to copy or redistribute. NVIDIA model cards, licensing and compatibility must be rechecked for the selected release.

## KEEP / ADOPT / ADAPT / RESEARCH matrix

| Capability | Existing MH02 baseline | Decision | Required delta and test |
|---|---|---|---|
| GPS/Redis and aggregate samples | valuable existing integration | KEEP + REWORK | one reader; age/fix/epoch validated, typed contracts; stale-data tests |
| Front continuous vlog | segmenting proof-of-concept exists | REWORK | immutable recoverable recording, exact coverage gaps, quota; 72h and power-cycle tests |
| Dual camera routing | inconsistent current paths | REWORK | physical front/cabin ownership and isolation; source-routing regression |
| Legacy cabin fatigue rules | business behavior valuable | KEEP behind adapter | sample-specific freshness, parity replay and controlled GPU migration |
| OpenCV CPU / OpenVINO front detector | not a proven NVIDIA GPU foundation | REPLACE incrementally | benchmark TensorRT/DeepStream first; preserve event contract |
| Pedestrian/vehicle detector | mining scene-specific proof missing | RESEARCH -> ADAPT | mine dataset and camera calibration; false positive/hour + per-scenario recall |
| Warning policy | detection != hazard | NEW governed domain module | geometry/zone/speed/time-to-collision assumptions with operational signoff |
| Evidence VTT/MP4 | current overlay/timing defects | REWORK | PTS-aligned canonical metadata, immutable source hash, derived MP4; replay tests |
| Fleet configuration/deployment | not ready for mass production | NEW | fleet inventory, unit config validation, signed release, staged OTA/rollback |
| Operator/fleet dashboard | existing prototype UI | KEEP + HARDEN | auth, access audit, offline health, evidence trust & coverage |
| Optional radar / distance sensing | no validated camera-only distance | RESEARCH | feasibility/calibration and cost-benefit; no safety performance promises |

## Domain-specific model selection protocol

**Candidate A:** NVIDIA DashCamNet on TensorRT/DeepStream.  
**Candidate B:** small commercial-license-approved YOLO model exported to TensorRT FP16.  
**Candidate C:** specialized models (PeopleNet + TrafficCamNet) only if measured improvement warrants extra complexity.

For all candidates collect the *same*, legally authorized and de-identified mine-site clips with annotations for:
- pedestrians at multiple distances/postures, occlusion, PPE, near-road and off-road;
- DT, SDT, light vehicle, excavator and other relevant mobile equipment; model taxonomy must be explicit;
- day/night, dust, glare, rain, camera vibration and dirty/obstructed lens;
- stationary and moving own vehicle, fast crossings and no-hazard scenes.

Report per-class precision/recall, false warnings/hour, p95 detection-to-warning latency, tracking discontinuity, CPU/GPU/RAM/temperature/power, frame drops, and **front vlog coverage while running the combined front + cabin workload**. Include dataset version, hardware/BSP version, model checksum, inference calibration and evaluation scripts. Quantitative pass thresholds require signoff from Mine Operations/Safety and have not yet been decided.

## Operator and commercial implications

1. The installation kit is part of the product: camera mount geometry, lens cleaning access, stable connectors, wiring, surge/ignition shutdown, thermal and vibration limits.
2. A *degraded mode* must be explicit: "camera obstructed", "inference unavailable", "GPS stale", "recording gap", "storage critical". Never show a green safety state solely because no objects were detected.
3. Human factors: prioritize relevant alerts, suppress repeated nuisance alarms by governed hysteresis, and log ruleset/version behind every alert.
4. Event evidence is a verifiable derivative of original footage, with retention/consent/access rules suited to deployed sites.
5. Commercial distribution requires third-party software and pretrained-model license, model weight provenance, SBOM, field support and security update commitments.
6. **Scope of claims:** until independently validated, call it *driver assistance / situational awareness*; do not claim validated collision avoidance, safety certification or quantified risk reduction.

## Related internal documents

- [Agent development rules](../../AGENTS.md)
- [Target architecture](../architecture/target-architecture.md)
- [Industrial architecture decision](../architecture/adr/0001-industrial-product-foundation.md)
- [Implementation roadmap](../operations/industrial-readiness-roadmap.md)
- [Release gates](../operations/release-gates.md)
