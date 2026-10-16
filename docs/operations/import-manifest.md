# Original archive import / publication policy

**Input:** user-provided `mh02model.zip` (2026-10-17), imported into new public GitHub repository. Baseline tree preserves `mh02model/` layout for easier comparison. This is not an assertion that all deployed files are identical.

## Deliberate omissions

- All `__pycache__/` and `*.pyc` generated cache.
- Proprietary/legacy Windows distributables: `wsay.exe`, `openh264-2.3.1-win64.dll`, and `alert.wav` (review binaries/media licensing and purpose before redistributing).
- Transient `Checking if port in use...` and zero-byte ad-hoc local device note.
- Device-specific original configuration; never publish secrets or active IPs.

## Transformations

- `mh02model/files/configs/{*.json,mh02.conf}` rewritten with redacted documentation IPs (`192.0.2.10`) and RTSP example-only usernames/passwords, then renamed `*.example`. The real deployed config should be managed in private fleet provisioning; **do not simply rename `.example` and run in a production unit**.
- `mh02model/apps/mh02/rtsp_cam.py` removed embedded RTSP secret and now reads the URI from environment variable `MH02_LEGACY_RTSP_URL`.
- The original static audit, NX addendum and two strategy docs copied under `docs/` unchanged; some audit references therefore still refer to the original ZIP paths and legacy version research date.

## Required future cleanups

1. Move all config to typed validated environment/config files with secure injection and versioned schema; document defaults and migration.
2. Require independent security review for any distribution of model weights, binaries or sample footage.
3. Verify no secrets ever entered Git history; a redaction in later commits cannot undo a first-push leak.
4. Obtain on-device inventory and update dependency/version matrix before creating deployable artifacts.
