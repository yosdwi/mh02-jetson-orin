# MH02 Jetson Orin — Production Readiness & Mass-Deployment Audit

**Tanggal:** 17 Oktober 2026  
**Status:** STATIC CODE AUDIT COMPLETE — **NO-GO for mass production**  
**Basis:** `mh02model.zip`, `JETSON_GSTREAMER_RUNTIME.md`, `JETSON_IMPLEMENTATION_STRATEGY.md`  
**Batas verifikasi:** Audit offline atas source terlampir, bukan inspeksi repository Git terkini atau runtime Jetson fisik. Tidak ada akses ke JetPack/L4T, varian board, kamera, disk aktual, tegrastats, maupun dataset lapangan. Klaim performance, GPU acceleration, reliability 24/7, detection accuracy, dan hardware encoding aktual **belum tervalidasi**.

## 1. Executive decision

**NO-GO untuk mass deployment pada baseline ZIP ini.** Yang tersedia sudah baik sebagai **PoC dan fondasi migrasi**: pemisahan service, typed event/aggregate, GStreamer pipeline, SQLite WAL, sidecar VTT, klip evidence dan web dashboard. Namun ada blocker correctness, evidence integrity, camera routing, storage, fleet security, deployment, dan GPU inference. Selain itu fitur yang baru diminta—vlog front dan deteksi pedestrian/kendaraan native NVIDIA—**belum sama-sama terimplementasi end-to-end**.

### Klasifikasi

| Area | Status | Keputusan |
|---|---|---|
| Legacy GPS & business logic | Useful compatibility baseline | **KEEP + EXTRACT** kontrak, jangan mempertahankan frame-copy path sebagai produksi |
| GStreamer USB camera + segmented MP4 | Partial prototype | **REWORK + HARDEN** lifecycle, timestamp, segment validity, reconnect |
| NVIDIA codec path | Proposed, not measured | **VERIFY** per Jetson SKU, JetPack/L4T, plugins |
| Front pedestrian/vehicle inference | Legacy code only | **REWORK** → native NVIDIA inference service |
| Fatigue cabin | CPU compatibility, wrong default source | **REWORK** routing dan freshness; domain tetap cabin |
| GPS/aggregate/store | Basic functional | **HARDEN** freshness, ordering, epoch/boot identity, retention |
| VTT + alert clips | Basic output | **REWORK** evidence timing and atomic publish; optional burn-in derivation |
| Web/media access | Internal PoC | **HARDEN** authentication, authorization, network isolation |
| systemd packaging and fleet | Service examples | **BUILD** versioned package, provisioning, rollout/rollback, fleet observability |
| Tests and release gates | 0 shipped tests found | **BUILD** CI, Jetson-in-the-loop, soak, fault injection |

## 2. Scope dan hasil pemeriksaan yang benar-benar dilakukan

- ZIP: 105 file non-directory; 59 Python files (48 under `apps/mh02`, 11 under `runtime/mh02_runtime`); 9 systemd units. Ada dua dokumen pendamping.
- Parsing source (`compile(...)`, no imports): **59/59 success**; ini *syntax-only* bukan test runtime.
- `jetson_gstreamer_runtime.py --camera-id front --dry-run --print-pipeline`: **success**; ini membangun string pipeline, tidak menginisialisasi kamera/GStreamer NVIDIA.
- Probe terisolasi menggunakan Pydantic/SQLite dan source runtime: **stale 10-minute fatigue flag menghasilkan satu alert** melalui empat aggregate sample; **stale GPS 2-day old tetap `valid=True`**. Source input tidak diedit.
- Dalam ZIP tidak ditemukan file test `test_*.py` atau artifact model `.onnx`/`.engine`/`.weights`/`.pt`/`.etlt`. Aplikasi juga tidak memiliki manifest deploy/build lengkap di root ZIP.
- Environment audit offline ini tidak memiliki `gi`, `pyserial`, `pyarrow`, `redis`, atau `mediapipe`; **GStreamer/Jetson runtime tidak dieksekusi**. Tidak ada klaim bahwa dependency ini tidak terpasang di perangkat Jetson sebenarnya.

## 3. P0 — blocker yang harus diperbaiki sebelum pilot operasional

**P0-01 — Fatigue camera salah sumber secara default.**  
`runtime/systemd/mh02-fatigue.service:11`, `runtime/mh02_runtime/fatigue_service.py:73-77`: fatigue source menunjuk `/live/front.m3u8`. Face landmark/closed-eye/yawning adalah fungsi *cabin*, bukan front road. Sementara recorder hanya memproduksi front. Tambahkan `camera_id` eksplisit, konfigurasi 2-camera dengan source terpisah, dan fail closed ketika cabin source tidak tersedia. **Jangan mengganti front dengan cabin di semua cabang; masing-masing memiliki video domain berbeda.**

**P0-02 — Data fatigue lama dapat memicu alert baru. Terbukti lewat probe.**  
`runtime/mh02_runtime/aggregate_service.py:64-76` selalu menyertakan `store.latest_fatigue()` tanpa age check, dan `runtime/mh02_runtime/alert_service.py:30-36,86-90` memakai boolean tersebut sebagai current signal. Satu flag `closed_eyes=True` yang berhenti diperbarui dapat dianggap berlangsung dua detik dan memicu alert. Perbaiki dengan per-event source timestamp, maximum detector age, source frame ID/PTS, confidence, heartbeat, state `UNKNOWN`/`STALE`; trigger memakai consecutive fresh detections / event time, bukan polling snapshot lama.

**P0-03 — GPS valid stale; tidak ada batas usia validitas. Terbukti lewat probe.**  
`runtime/mh02_runtime/store.py:70-75`, `runtime/mh02_runtime/aggregate_service.py:73`, `runtime/mh02_runtime/web_server.py:198-201`: `valid` GNSS dari snapshot lama tetap ikut sample agregat. `gps_service.py:46-69` tidak memvalidasi NMEA checksum, tidak mengikat fix/speed/koordinat konsisten ke waktu fix, serta tidak membersihkan posisi saat sinyal hilang. Tambahkan `fix_observed_at_utc`, `gps_age_ms`, `quality`, `valid_until`, checksum, bounds dan status `NO_FIX`/`STALE`/`INVALID`. Jangan pakai stale GPS untuk evidence geolocation atau risk rules.

**P0-04 — Sidecar dan MP4 belum sinkron ke media PTS secara otoritatif.**  
`runtime/mh02_runtime/vlog_service.py:92-103,147-164,224-238`: titik awal VTT dimulai saat signal `splitmuxsink-fragment-opened` diproses (`time.monotonic_ns()`), **bukan** dari video buffer PTS / first presentation timestamp. Durasi ditulis dari wall/monotonic saat fungsi dipanggil, bukan ffprobe/media duration. `1.2s` VTT cue per sampel 1Hz menyebabkan cue overlap. Outcome: overlay saat playback, event clipping, timestamp, dan evidence dapat meleset. Gunakan canonical sample/frame clock mapping + segment start PTS + per-frame timestamp, expose uncertainty, dan verifikasi A/V timestamp versus GNSS. VTT ialah view, bukan source of truth.

**P0-05 — Fragment dianggap complete sebelum finalization terbukti.**  
`runtime/mh02_runtime/vlog_service.py:185-189,235-238`: `splitmuxsink async-finalize=true` tetapi metadata segmen ditandai `complete=True` ketika *next fragment opened* (`subtitles.close()` default true), bukan pada `splitmuxsink-fragment-closed`, cek index/duration/integrity, dan durable disk sync. Dengan crash atau fragment finalization lambat, file dapat dipublikasikan salah. Implement state `OPEN -> FINALIZING -> VERIFIED -> PUBLISHED` dengan temp-file/atomic rename dan crash recovery on startup. Jangan menyimpulkan `moov` ditemukan saja cukup.

**P0-06 — Alert clip dapat mismatch media boundary/keyframe versus wall time.**  
`runtime/mh02_runtime/alert_clip_service.py:100-136,208-235,253-300`: seek dengan `KEY_UNIT` (boleh tidak frame-exact), metadata output menyatakan interval target seolah exact, VTT dipotong lewat timestamp turunan wall. Multi-segment concat menggunakan TS bytes join tanpa assert continuity/timestamp/discontinuity. Tambahkan actual decoded media duration/PTS dan out-of-range reporting, gap/overlap detection, boundaries tests (± keyframe / spanning segments), serta checksum dan provenance setiap input. Untuk trimming frame-accurate, pilih strategi recode hanya pada clip akhir bila perlu; original MP4 tetap raw.

**P0-07 — Security web/media terbuka pada LAN.**  
`runtime/systemd/mh02-web.service:9` bind `0.0.0.0:8080`; `runtime/mediamtx.yml:1-10` expose RTSP/WebRTC, wildcard WebRTC origin, publisher `all_others`. `runtime/mh02_runtime/web_server.py:194-305` menyediakan unduh video, metadata, GPS tanpa authentication/authorization. Data driver, lokasi, dan footage tidak boleh terbuka ke jaringan produksi. Tambahkan identity/authN/authZ, per-unit RBAC, bind/tunnel/VPN, TLS at trusted boundary, deny-by-default MediaMTX paths dan publisher tokens, audit access log, retention/privacy policy. `allowOrigins` bukan authentication.

**P0-08 — Tidak ada storage backpressure/quota/retention untuk rekaman dan evidence.**  
`runtime/mh02_runtime/vlog_service.py:178-194,205-250`, `web_server.py:146-170`, `runtime/README.md`: 4 Mbps konstan kira-kira 43.2 GB/hari untuk satu stream (tanpa overhead), ~1.3 TB/30 hari; satu download bundle membuat ZIP sementara sebesar video dan berpotensi meningkatkan disk usage. Tidak ditemukan capacity budget, watermark, evict policy, separate critical-alert retention, I/O pressure control atau disk-full recovery. Implement priority-tier storage, disk reserves, pressure alarms, periodic reconciliation, immutable evidence pins, configurable retention dan cleanup berurutan.

**P0-09 — Kamera/network restart, USB node, recorder failover belum kuat.**  
`vlog_service.py:205-250` pada GStreamer ERROR/EOS hanya set stop; restart level systemd. `pipeline_description():178-194` queue tidak dibatasi explicit pada recorder/HLS/RTSP branches. Timestamp/pipeline restart, partial file salvage, exponential reconnect dan camera stable path belum masuk service. Tambahkan watchdog per-source, bounded leaky *preview/inference* branches dan non-leaky recording policy dengan storage backpressure, restart budgets, cam UID discovery; uji unplug/replug/network outage.

**P0-10 — SKU Jetson belum di-lock, codec assumption salah untuk Orin Nano.**  
`jetson_gstreamer_runtime.py:19-26,133-156`, `vlog_service.py:180-194` memerlukan `nvv4l2h264enc`. NVIDIA menyatakan Jetson **Orin Nano tidak memiliki NVENC**; Orin NX dan AGX Orin berbeda. SKU dan JetPack aktual belum terbukti. Jika Orin Nano: lebih efisien gunakan **kamera yang memberi H.264/H.265 native untuk passthrough (tanpa re-encode)** jika cocok, atau pertimbangkan SKU NX untuk encode terus-menerus. Bila video UVC MJPEG, assess software encode budget dengan beban inference nyata. Tidak boleh mengklaim hardware encode tanpa `gst-inspect`, `tegrastats`, serta stream verification pada device target.

**P0-11 — Belum ada native NVIDIA front pedestrian/vehicle inference pada runtime baru.**  
`apps/mh02/detectors/CollisionDetector.py:3,210-231,243-244` masih OpenVINO `IECore` (legacy, `device_name='GPU'` **bukan** bukti NVIDIA GPU), hard-coded YOLOv4-tiny & classes `[0,2,5,7]`. Runtime baru hanya mencakup `fatigue_service` CPU kompatibilitas; tidak ada `front_inference_service`, `nvinfer` config, TensorRT engine, model artifact, dataset calibration atau tracker. Buat detector service yang menghasilkan structured object/track events dari front stream. Jangan mengklaim deteksi kendaraan/pedestrian sudah aktif di Jetson runtime.

**P0-12 — Produksi dan fleet operations belum ada.**  
`runtime/systemd/*`: hardcoded user/path, `Restart=always`, tidak memiliki `WatchdogSec`, `StartLimit...`, sandboxing, hardening fs, per-district/profile provisioning, pinned image, signed OTA/A-B, rollback, config migration, golden image, or clear service dependency recovery. `requirements-jetson.txt` tidak memasukkan OpenCV/MediaPipe/GI bindings yang digunakan fatigue/GStreamer; version pin compatibility JetPack juga belum dibuktikan. Implement reproducible image/pinned dependency SBOM, fleet identity, staged OTA rollback, fleet policy/config, health watchdog, provenance & metrics. Semua ini **release blockers** untuk mass rollout.

## 4. P1 — correctness, recoverability, scalability

**P1-01 — Alert lifecycle tidak mempunyai gap/unknown state.** `alert_service.py:83-113,116-132`: state `post` melewati setiap `active` selama post window; event close pada satu `False`, meskipun detector hilang atau video loss. State machine harus memisahkan `NOT_DETECTED`, `DETECTED`, `NO_FRAME`, `STALE`, dan `ERROR`, dengan hysteresis dan bounded gap tolerance. Alert harus menyertakan `camera_id`, `model_version`, `source_status`.

**P1-02 — Persistence satu database dengan multi-process contention.** `store.py:22-25,59-173`: WAL membolehkan concurrency tetapi setiap service membuka koneksi/write; per-sample `DELETE...NOT IN (SELECT...LIMIT)` dan file replace snapshot per detik menambah write amplification. Stress-test WAL checkpoint, lock timeout, fs wear, corruption/power loss; tambah indexes/schema migrations, batch writes, busy timeout/jitter, retention by indexed cutoffs, periodic VACUUM/checkpoint schedule, integrity check.

**P1-03 — Datalog replay tidak durable exactly-once.** `datalogger_service.py:76-131`: flush tutup jam menulis Parquet sekali, lalu bila file existing langsung `return`; tidak ada watermark/ledger per-file & gap reconciliation. Restart jam berjalan mereplay hingga 86.400 row, tetapi saat interval sudah ter-flush dan historical sample datang, current code tidak menggabungkannya. Tambahkan committed cursor, hourly manifest, expected range, gaps, checksum, atomic data+manifest publish, optional corrections/upserts.

**P1-04 — Clock epoch/identity hilang saat reboot/step NTP.** `models.py`, `aggregate_service.py:64-76`, `vlog_service.py:99-125`: `time.monotonic_ns()` restart tiap boot, wall clock dapat step NTP. Waktu dari GPS serial ada dua jenis (`UTC received` vs GNSS time). Perlu `boot_id`, `stream_epoch_id`, `clock_source`, `clock_sync_status`, `clock_offset/error_bound_ms`, `frame_pts_ns`, `capture_time_utc` + `processed_time_utc`, dan explicit drift monitor.

**P1-05 — Layout/overlay evidence belum canonical.** `vlog_service.py:157-164` menulis tiga cue per sampel dengan line 5/12/88; berpotensi overlap antar player. Pertahankan MP4 raw + normalized metadata sebagai evidence utama, dan generate **derived burned-in alert evidence** memakai deterministic font/layout, video timestamp, unit/channel, class/confidence/event; label `DERIVED`, hash original dan parent ID. VTT tetap untuk UI interactive tetapi tidak boleh jadi satu-satunya metadata.

**P1-06 — Camera hardware discovery/conflicts.** Pipeline `v4l2src device=/dev/video0` raw hardcoded. Jika USB device order berubah pada cold-boot, source bergeser. Gunakan `/dev/v4l/by-id`/udev rules, capability/format negotiation startup, camera serial, board port topology, capture node checks, fallback disabled by default.

**P1-07 — Model correctness dan collision risk.** `CollisionDetector.py:38-54,172-208,233-245`: heuristik bbox width sebagai jarak/TTC terlalu rapuh untuk kamera moving mining truck: perspektif, ukuran objek, slope, pitch, mounting/FOV, occlusion. Pisahkan **object detection** dari **pedestrian/vehicle warning**. Warning harus berbasis tracked trajectory, calibrated road ROI, TTC/proximity confidence, ego speed/heading, physical validation; jangan mengklaim safety-grade collision avoidance dari bbox width.

**P1-08 — Health dashboard terlalu optimistis.** `web_server.py:237-265` 24h status hijau berdasarkan jumlah durasi rekaman dan row datalog ≥80% target (bukan interval coverage), bahkan segment overlap bisa double-count. Hitung union coverage, missing intervals, playable MP4, age of last frame, GPS freshness, inference and storage state; separate `online`, `degraded`, `offline`, `unknown`.

**P1-09 — Source/config trust & reproducibility.** `apps/mh02/mh02_front.py:14,85-103` import `classes.Camera` sementara ZIP tidak menyertakan `apps/mh02/classes/Camera.py`. Legacy Windows-style paths tidak portable. Engine model weights tidak ikut ZIP. Replace ad-hoc packaging dengan explicit contracts/manifest, model artifact registry+checksums, runtime image compatibility lock.

**P1-10 — Logging dan metrics.** Services standard Python INFO log, no structured spans/health endpoints per module, no video FPS/drop/PTS gap/camera reason/CPU/GPU thermals/storage metrics. Implement Prometheus/local JSON heartbeat, sampled `tegrastats`, disk SMART, camera unplug, stream loss, post-processing backlog, alerts per unit and status age. Prevent logging GPS/credential payloads verbatim.

**P1-11 — Web streaming recovery** `web/app.js:16-52` peer connection basic WHEP; no signaling reconnect/close/dispose handling. HLS fallback, resource cleanup, network error classification, secure-origin constraints & deployed reverse proxy must be tested.

**P1-12 — Evidence immutable provenance and chain of custody absent.** Each video/clip/datalog needs SHA-256, `recording_id`, source camera, device and unit ID, software and model version, segment boundaries, capture clock quality, event source, derivation lineage and atomic manifest. Alert clips must never silently overwrite originals or mutate metadata to match desired duration.

## 5. Recommended production architecture (incremental, no big-bang legacy rewrite)

```text
Cameras (distinct IDs/UIDs)                    EC25 + vehicle telemetry
  front H264/MJPEG / cabin H264/MJPEG                |
        |                                     GPS service + Redis bridge
        v                                             |
 Ingest / Media Supervisor -- boot_id + clock / PTS ---+
        |
        +-- RAW RECORDING branch --> MP4 fMP4/segments --> Finalize + verify --> Evidence manifest
        |                                     |                         |
        +-- PREVIEW branch --> MediaMTX --> secured web/player            |
        |                                                               |
        +-- FRAME/INFERENCE branch --> DeepStream (Jetson-appropriate)    |
                                           |                              |
                              NVIDIA/TensorRT detector + nvtracker        |
                                  |                |                      |
                            Person/Vehicle      Cabin fatigue            |
                                  |                |                      |
                                  +-- Structured Events --> Rule engine --+
                                                                |
                                        Alert lifecycle + pre/post clip export
                                                                |
                                             Metadata + VTT + derived burn-in MP4
                                                                |
                                         Upload queue / fleet operations / observability
```

**Key invariant:** satu camera ingest yang terpercaya per kamera; recording raw tidak menunggu inference; event uses frame timestamp not aggregate poll time. **Safety degradation:** apabila inference mati, video recording tetap hidup; dashboard menampilkan inference unavailable, bukan falsely healthy.

## 6. Front camera model evaluation: lightweight and native NVIDIA

Model hanya boleh dipilih setelah jetson SKU + camera optical configuration diketahui dan benchmark menggunakan *video mining site nyata*. Jangan pakai angka mAP lintas dataset sebagai perbandingan langsung.

| Candidate | Peran | Kelebihan | Tradeoff / gate |
|---|---|---|---|
| **DashCamNet** (NVIDIA TAO) | Native NVIDIA proof baseline untuk objek dari moving camera | Contoh official DeepStream; mudah baseline TensorRT | Classes/domain tidak otomatis cocok excavator/DT/SDT/pedestrian; evaluate coverage |
| **PeopleNet + TrafficCamNet** (NVIDIA TAO) | Person + vehicle baseline dua model | Pretrained/reference DeepStream | 2 models cost, domain shift mine site and truck classes; calibrate |
| **YOLO lightweight (mis. YOLO11n / YOLOv8n) → ONNX → TensorRT FP16** | Candidate unified person/vehicle | Satu model, community ecosystem, model variants | Export/plugin compatibility, licenses, image normalization/NMS, model drift, re-training mining data; **not verified** fastest/most accurate here |
| **INT8 TensorRT** on validated FP16 detector | Optimization phase | Potential more throughput/reduced memory | Representative calibration dataset + accuracy regression validation essential |

**First choice for benchmarking:** DashCamNet or NVIDIA PeopleNet+TrafficCamNet as reference pipeline, paired against one small YOLO TensorRT FP16. Select by required mine-site recall/false alarms and *total device* performance, not FPS alone. Use `nvinfer`/TensorRT on supported DeepStream version and `nvtracker` for temporal stability. Collision/pedestrian *warning* requires separate domain-calibrated decision rules.

**IMPORTANT version gate:** NVIDIA DeepStream 8.0 support matrix lists **Jetson Thor** (not Orin) for Jetson. The established **DeepStream 7.1 + JetPack 6.1** combination supports Jetson Orin; pin exact actual supported SKU/JetPack version before install. DeepStream 8.0 is **not** a default upgrade path for Orin. Source: https://docs.nvidia.com/metropolis/deepstream/8.0/text/DS_Installation.html

**IMPORTANT encoder gate:** Orin Nano lacks NVENC, unlike Orin NX. Source: https://docs.nvidia.com/jetson/archives/r36.5/DeveloperGuide/SD/Multimedia/SoftwareEncodeInOrinNano.html

**NVIDIA model references:** https://docs.nvidia.com/metropolis/deepstream/8.0/text/DS_TAO_integration.html and https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_plugin_gst-nvinfer.html

## 7. Suggested implementation work packages (non-overlapping)

| Batch | Priority | Goal and deliverables | Exit evidence |
|---|---|---|---|
| 0. Freeze hardware + source of truth | P0 | Jetson SKU, JetPack/L4T, camera UIDs/formats, runtime manifests, current deployed services, baseline measured load | Versioned inventory + baseline log, no assumptions |
| 1. Evidence correctness and clocks | P0 | freshness contract, source frame IDs/PTS, monotonic->UTC mapping, boot epoch, normalized canonical event metadata, tests | stale signals cannot trigger; GPS unknown after expiry; clip timestamp error measured |
| 2. Recording hardening | P0 | one-ingest per camera, queue rules, keyframe/fragment closed, crash recovery, storage quotas, raw immutability | 24/7 segmented archive, unplug/power failure tests, no premature `complete` |
| 3. Security + deploy | P0 | authenticated web/media, pinned dependencies, systemd hardening, config/secrets, OTA/rollback, smoke tests | network checks, recoverable rollbacks, no unauthenticated footage |
| 4. Front inference benchmark | P0 | NVIDIA TensorRT + model A/B (DashCamNet vs small YOLO), track IDs, class mapping, events | labelled test set, Jetson CPU/GPU/RAM/power/thermal + recall/false positive evidence |
| 5. Front domain rules and overlay | P1 | pedestrian/vehicle warning, calibrated ROI, risk semantics, raw+derived alert MP4 + VTT | correct site scenarios, false alarm budget, playback and hashes |
| 6. Cabin migration | P1 | separate cabin source, preserve fatigue semantics, migrate CPU compatibility behind adapter | before/after event parity and measured resource usage |
| 7. Soak/canary/fleet gates | P0 | hardware-in-loop automated test, 72h + 7-day field soak, staged rollouts/rollback | signed release manifest and operations signoff |

## 8. Go-live / mass production acceptance gates (proposed targets, adjust with actual hardware and operational requirements)

**Reliability and storage:**
1. No service crash/reboot loop or unbounded RAM/CPU growth in **72h bench soak** and **7-day pilot**; sampled at least hourly and during heavy load. No disk fill without protective deletion/stop states and explicit alert.
2. `power cut during open segment` → retained finalized segments playable, unfinalized segment recovered or clearly `INCOMPLETE` without phantom success. Test across segment boundaries, concurrent download, disk full, device reboot, USB detach.
3. Recorded coverage **≥99.5% of available camera capture time** in stable test environment (suggested initial SLO), with all gaps identifiable; exact threshold to be agreed based on mine connectivity/power realities.
4. Video/audio where applicable, metadata and alert event timestamps validated against frame PTS and trusted UTC. Proposed desired absolute timestamp error **≤250 ms** for video-event overlay on healthy clock; report measured uncertainty rather than fabricate a time.

**Inference:**
5. Define minimum recall/precision and false-alert rate per class using a curated **mining dataset** (night/IR, rain, dust, glare, backlight, vehicle vibrations, pedestrians behind vehicles, near/far truck). No automatic safety-critical warning until human-verified tests.
6. Benchmark at true target front resolution 1080p30 recording + live + inference + cabin concurrently, and target Jetson power profile, ambient temperature. Proposal: end-to-end **p95 inference latency <150 ms** at configured sampled inference FPS (e.g. 10–15 FPS initial) *only if measured on actual board*. Frames can be sampled for inference but never degrade required raw recording.
7. Model exported to `ONNX` then TensorRT with checksums, labels, preprocessing, postprocessing tested against reference outputs, and version pinned per device. FP16 first; INT8 only after independent calibrated accuracy checks.

**Fleet and security:**
8. Every service reports `OK`, `DEGRADED`, `STALE`, `ERROR` with reason; fleet dashboard can distinguish `camera online` from `inference healthy` and `recording complete`.
9. Authenticated access to live/archived video and GPS; API routes block unauthorized users; device identity, secrets, remote access and retention approved. Upload/download uses authenticated resumable transfer and checksum.
10. Signed and staged OTA (lab → small canary → district pilot → wider fleet), idempotent install/provision, health-gated rollback and failed-version quarantine.

**Evidence integrity:**
11. Each raw MP4 and derived alert file verified by media probe + cryptographic hash; derived overlay names source recording + clip algorithm + model/software version; no silent modifications to raw.
12. Boundary crossing event validated with replay scenarios: event spans 2 or 3 segments; duplicate event restart; post-window missing; GPS/fatigue frame stale; reboot during export; uploader offline; signed archive reproducibility.

## 9. Collect these facts from the actual Jetson before implementation freeze

Run read-only commands on one **representative target board**, recording stdout and exact package versions; do not paste credentials:

```bash
cat /etc/nv_tegra_release || true
cat /etc/os-release
dpkg-query -W '*nvidia-l4t*' '*deepstream*' 2>/dev/null
cat /proc/device-tree/model 2>/dev/null | tr -d '\0'; echo
sudo nvpmodel -q
which gst-inspect-1.0 && gst-inspect-1.0 nvv4l2decoder && gst-inspect-1.0 nvv4l2h264enc
which gst-inspect-1.0 && gst-inspect-1.0 nvinfer
v4l2-ctl --list-devices; find /dev/v4l/by-id -maxdepth 1 -type l -ls 2>/dev/null
lsblk -o NAME,MODEL,SIZE,ROTA,FSTYPE,MOUNTPOINTS
systemctl --no-pager --type=service --state=running | grep -Ei 'mh02|mediamtx'
tegrastats --interval 1000
```

With the actual camera running, also capture `gst-discoverer-1.0`/V4L capabilities, `ffprobe` of a finalized raw sample, 10-minute thermal/CPU/GPU/RAM/storage metrics, and queue/drop counters. `tegrastats GR3D` alone is not a definitive measure of TensorRT; correlate named runtime engine and accelerator metrics.

## 10. Change policy for execution agent

- Work from original repository + current branch after checking `AGENTS.md`, versions, deployed service definitions; **do not treat this ZIP as latest Git source** if repo history differs.
- Do not overwrite/replace legacy detector code until compatibility tests and event equivalence exist. Keep adapter boundaries and gated migration.
- In each PR: **evidence lines → failing test → minimal patch → regression test → on-device verification**. Do not claim runtime performance from mock-only, compile-only, or dry-run tests.
- Keep `front` and `cabin` independent camera identities, retention classes and inference pipelines; canonical data/events shared. Do not share a false default source for both cameras.
- Protect original video. Burn-in overlays only into **derived evidence** (for UI convenience and portability) with `source_sha256`, `derived_sha256`, and render/version manifest.
- Feature flags per district/unit, staged rollout + rollback. A detector failure must not stop raw capture or falsely imply no hazards.
- Stop rollout immediately on repeated missing evidence, incorrect timestamps, stale alert storms, disk full, thermal throttling, unbounded RAM growth, or unauthorized video access.

## 11. Explicit remaining unknowns

Actual Jetson SKU (Nano/NX/AGX), JetPack/L4T, GStreamer and DeepStream versions, powered USB topology, front/cabin sensor models and actual bitstreams, recording disk endurance/free space, environmental power/thermal/ignition cycle, camera timestamps, update infrastructure and backend uploader, current model weights, annotated mine-site sample dataset, and field safety requirements. These **cannot be resolved from the ZIP** and must be marked as unverified—not filled in with assumptions.

---

**Audit interpretation:** *Syntax pass ≠ runtime pass; PoC output ≠ evidence integrity; NVIDIA codec plugin existence ≠ encoder hardware on every Orin; existing face detector ≠ NVIDIA GPU; model detection ≠ collision risk estimation; one successful MP4 ≠ 24/7 mass production readiness.*
