from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .inference_contracts import DetectionObservation, WarningCandidate


class AdvisoryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    confidence_threshold: float = Field(default=0.5, ge=0, le=1)
    classes: Tuple[str, ...] = ("person", "car", "truck", "bus", "motorcycle", "two-wheeler")


def candidates_for(
    observations: Iterable[DetectionObservation],
    policy: AdvisoryPolicy,
) -> List[WarningCandidate]:
    allowed = {item.lower() for item in policy.classes}
    result: List[WarningCandidate] = []
    for observation in observations:
        if observation.object_class.lower() not in allowed:
            continue
        if observation.confidence < policy.confidence_threshold:
            continue
        result.append(
            WarningCandidate(
                warning_id=f"warning-{uuid.uuid4().hex}",
                created_at_utc=datetime.now(timezone.utc),
                source_kind=observation.source_kind,
                frame_id=observation.frame_id,
                media_pts_ns=observation.media_pts_ns,
                frame_ref=observation.frame_ref,
                object_class=observation.object_class,
                confidence=observation.confidence,
                track_id=observation.track_id,
                evidence={"camera_id": "front", "segment_id": None, "status": "pending"},
            ),
        )
    return result
