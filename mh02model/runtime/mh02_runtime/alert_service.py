from __future__ import annotations

import argparse
import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Dict, Literal, Optional, Tuple

from .models import AlertEvent, AggregateSample, FatigueStatus
from .diagnostics import configure_logging
from .store import RuntimeStore


LOGGER = logging.getLogger("mh02.alerts")
AlertType = Literal["closed_eyes", "yawning"]
ALERT_TYPES: Tuple[AlertType, AlertType] = ("closed_eyes", "yawning")
CURSOR_NAME = "alerts"


@dataclass
class Episode:
    alert_type: AlertType
    started_at_utc: Optional[datetime] = None
    event: Optional[AlertEvent] = None
    stale_since_utc: Optional[datetime] = None


def fatigue_status(sample: AggregateSample, max_age_seconds: float = 2.0) -> FatigueStatus:
    fatigue = sample.fatigue
    if fatigue is None:
        return "unknown"
    if not fatigue.is_fresh(sample.timestamp_utc, max_age_seconds):
        return "stale"
    return "fresh"


def active_for(sample: AggregateSample, alert_type: AlertType) -> bool:
    if fatigue_status(sample) != "fresh":
        return False
    fatigue = sample.fatigue
    if fatigue is None:
        return False
    if alert_type == "closed_eyes":
        return fatigue.closed_eyes
    return fatigue.yawning


def update_event(
    event: AlertEvent,
    state: Literal["active", "post", "complete"],
    ended_at_utc: Optional[datetime] = None,
    evidence_end_utc: Optional[datetime] = None,
    source_status: Optional[FatigueStatus] = None,
) -> AlertEvent:
    duration = event.duration_seconds
    if ended_at_utc is not None:
        duration = (ended_at_utc - event.started_at_utc).total_seconds()
    return event.model_copy(
        update={
            "state": state,
            "ended_at_utc": ended_at_utc if ended_at_utc is not None else event.ended_at_utc,
            "evidence_end_utc": evidence_end_utc if evidence_end_utc is not None else event.evidence_end_utc,
            "duration_seconds": duration,
            "source_status": source_status if source_status is not None else event.source_status,
        },
    )


def trigger_event(episode: Episode, sample: AggregateSample, pre_seconds: float) -> AlertEvent:
    started = episode.started_at_utc
    if started is None:
        raise RuntimeError("Cannot trigger an episode without a start timestamp")
    event_id = f"{episode.alert_type}-{started.strftime('%Y%m%dT%H%M%S%fZ')}"
    return AlertEvent(
        id=event_id,
        alert_type=episode.alert_type,
        state="active",
        started_at_utc=started,
        triggered_at_utc=sample.timestamp_utc,
        evidence_start_utc=started - timedelta(seconds=pre_seconds),
        camera_id=sample.fatigue.camera_id if sample.fatigue is not None else "cabin",
        boot_id=sample.boot_id,
    )


def process_sample(
    store: RuntimeStore,
    episodes: Dict[AlertType, Episode],
    sample: AggregateSample,
    trigger_seconds: float,
    pre_seconds: float,
    post_seconds: float,
    stale_gap_seconds: float = 2.0,
) -> None:
    for alert_type in ALERT_TYPES:
        episode = episodes[alert_type]
        source_status = fatigue_status(sample)
        if source_status != "fresh":
            if episode.event is None:
                episode.started_at_utc = None
                continue
            if episode.stale_since_utc is None:
                episode.stale_since_utc = sample.timestamp_utc
            if episode.event.source_status != source_status:
                episode.event = update_event(episode.event, episode.event.state, source_status=source_status)
                store.save_alert(episode.event)
            if episode.event.state == "active" and (sample.timestamp_utc - episode.stale_since_utc).total_seconds() > stale_gap_seconds:
                evidence_end = sample.timestamp_utc + timedelta(seconds=post_seconds)
                episode.event = update_event(
                    episode.event,
                    "post",
                    episode.stale_since_utc,
                    evidence_end,
                    source_status=source_status,
                )
                store.save_alert(episode.event)
            continue
        episode.stale_since_utc = None
        if episode.event is not None and episode.event.source_status != "fresh":
            episode.event = update_event(episode.event, episode.event.state, source_status="fresh")
            store.save_alert(episode.event)
        active = active_for(sample, alert_type)
        if episode.event is not None and episode.event.state == "post":
            continue
        if active:
            if episode.started_at_utc is None:
                episode.started_at_utc = sample.timestamp_utc
            if episode.event is None and (sample.timestamp_utc - episode.started_at_utc).total_seconds() >= trigger_seconds:
                episode.event = trigger_event(episode, sample, pre_seconds)
                store.save_alert(episode.event)
                LOGGER.info("Triggered %s alert %s", alert_type, episode.event.id)
            continue
        if episode.event is not None and episode.event.state == "active":
            evidence_end = sample.timestamp_utc + timedelta(seconds=post_seconds)
            episode.event = update_event(episode.event, "post", sample.timestamp_utc, evidence_end)
            store.save_alert(episode.event)
            LOGGER.info("Started post window for %s alert %s", alert_type, episode.event.id)
        elif episode.event is None:
            episode.started_at_utc = None


def finalize_post_windows(store: RuntimeStore, episodes: Dict[AlertType, Episode], now: datetime) -> None:
    for alert_type in ALERT_TYPES:
        episode = episodes[alert_type]
        event = episode.event
        if event is None or event.state != "post" or event.evidence_end_utc is None or now < event.evidence_end_utc:
            continue
        episode.event = update_event(event, "complete", event.ended_at_utc, event.evidence_end_utc)
        store.save_alert(episode.event)
        episode.started_at_utc = None
        episode.event = None
        LOGGER.info("Completed %s alert %s", alert_type, event.id)


def run(args: argparse.Namespace, stop: Event) -> None:
    store = RuntimeStore(Path(args.database))
    episodes: Dict[AlertType, Episode] = {alert_type: Episode(alert_type) for alert_type in ALERT_TYPES}
    for event in store.open_alerts():
        episode = episodes[event.alert_type]
        episode.event = event
        episode.started_at_utc = event.started_at_utc if event.state == "active" else None
    cursor = store.load_cursor(CURSOR_NAME)
    while not stop.is_set():
        samples = store.samples_after(cursor, limit=1000)
        for sample in samples:
            cursor = sample.sequence
            process_sample(
                store,
                episodes,
                sample,
                args.trigger_seconds,
                args.pre_seconds,
                args.post_seconds,
                args.stale_gap_seconds,
            )
            finalize_post_windows(store, episodes, sample.timestamp_utc)
        store.save_cursor(CURSOR_NAME, cursor)
        finalize_post_windows(store, episodes, datetime.now().astimezone())
        stop.wait(args.interval)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="MH02 fatigue alert lifecycle service")
    result.add_argument("--database", default="/var/lib/mh02/state/mh02.sqlite3")
    result.add_argument("--trigger-seconds", type=float, default=2.0)
    result.add_argument("--pre-seconds", type=float, default=7.5)
    result.add_argument("--post-seconds", type=float, default=4.5)
    result.add_argument("--stale-gap-seconds", type=float, default=2.0)
    result.add_argument("--interval", type=float, default=1.0)
    return result


def main() -> int:
    configure_logging("mh02.alerts")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    run(parser().parse_args(), stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
