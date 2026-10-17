from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from .evidence import overlay_lines
from .models import AggregateSample
from .store import RuntimeStore


class OverlayComposer:
    def __init__(
        self,
        store: RuntimeStore,
        camera_id: str,
        device_id: str,
        unit_no: str,
        font_size: int = 22,
        safe_margin: int = 24,
        diagnostics: bool = False,
        max_age_seconds: float = 2.0,
    ) -> None:
        self.store = store
        self.camera_id = camera_id
        self.device_id = device_id
        self.unit_no = unit_no
        self.font_size = font_size
        self.safe_margin = safe_margin
        self.diagnostics = diagnostics
        self.max_age_seconds = max_age_seconds

    def sample(self) -> Optional[AggregateSample]:
        return self.store.latest_aggregate()

    def lines(self, clock_source: str = "media_pts") -> Tuple[str, ...]:
        sample = self.sample()
        if sample is not None:
            age_seconds = (datetime.now(timezone.utc) - sample.timestamp_utc).total_seconds()
            if age_seconds < 0 or age_seconds > self.max_age_seconds:
                sample = sample.model_copy(update={"gps": None, "gps_health": None, "fatigue": None})
        if sample is None:
            return (
                "GPS UNKNOWN: --, --, --KM/H ACC:--",
                f"ID: {self.device_id or '--'} UNIT: {self.unit_no or '--'} CAM:{self.camera_id.upper()}",
                f"{datetime.now(timezone.utc).astimezone().strftime('%d-%m-%Y %H:%M:%S')} {self.unit_no or '--'} CLOCK:{clock_source.upper()}",
                f"AI {self.camera_id.upper()}: UNAVAILABLE",
            )
        base = overlay_lines(sample, self.camera_id, clock_source)
        if self.camera_id.lower() == "front":
            ai_line = "AI FRONT: INFERENCE ACTIVE" if sample.timestamp_utc else "AI FRONT: UNAVAILABLE"
        elif sample.fatigue is not None and sample.fatigue.is_fresh(sample.timestamp_utc, 2.0):
            fatigue = "ALERT" if sample.fatigue.closed_eyes or sample.fatigue.yawning else "NORMAL"
            ai_line = f"AI CABIN: {fatigue} EAR:{sample.fatigue.ear if sample.fatigue.ear is not None else '--'} MAR:{sample.fatigue.mar if sample.fatigue.mar is not None else '--'}"
        else:
            ai_line = "AI CABIN: UNAVAILABLE/DELAYED"
        return (*base, ai_line) if self.diagnostics else (*base, ai_line)

    def add_display_meta(self, pyds: Any, batch_meta: Any, frame_meta: Any) -> None:
        display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        lines = self.lines()
        display_meta.num_labels = min(len(lines), 16)
        for index, line in enumerate(lines[: display_meta.num_labels]):
            text_params = display_meta.text_params[index]
            text_params.display_text = line
            text_params.x_offset = self.safe_margin
            text_params.y_offset = self.safe_margin + index * (self.font_size + 8)
            text_params.font_params.font_name = "Sans"
            text_params.font_params.font_size = self.font_size
            text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
            text_params.set_bg_clr = 1
            text_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.65)
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)


def identity_values(path: Path) -> Tuple[str, str]:
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "UNKNOWN", "UNKNOWN"
    return str(payload.get("DEVICE_ID", "UNKNOWN")), str(payload.get("UNIT_NO", "UNKNOWN"))
