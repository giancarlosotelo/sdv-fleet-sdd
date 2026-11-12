from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any

from fleet.cloud.storage import Alert


class AlertBook:
    """Edge-triggered alert lifecycle (spec REQ-081..083). In-memory state only; no I/O."""

    def __init__(self, new_id: Callable[[], str], open_alerts: Iterable[Alert] = ()):
        self._new_id = new_id
        self._hazard: dict[str, Alert] = {}
        self._offline: dict[str, Alert] = {}
        for alert in open_alerts:
            book = self._hazard if alert.kind == "hazard" else self._offline
            book[alert.vehicle_id] = alert

    def open_hazards(self) -> list[Alert]:
        return list(self._hazard.values())

    def hazard(self, msg: dict[str, Any], t1_ms: int, trip: int | None) -> list[Alert]:
        """Returns the alerts that changed: the resolved previous one and/or the newly opened one."""
        vid = msg["vehicle_id"]
        current = self._hazard.get(vid)
        incoming = (msg["hazard_type"], msg["severity"])
        if current and (current.hazard_type, current.severity) == incoming:
            return []
        changed = []
        if current:
            changed.append(replace(current, resolved_ms=t1_ms))
            del self._hazard[vid]
        if msg["hazard_type"] != "none":
            opened = Alert(
                id=self._new_id(),
                vehicle_id=vid,
                kind="hazard",
                hazard_type=msg["hazard_type"],
                severity=msg["severity"],
                t0_ms=msg["t0"],
                t1_ms=t1_ms,
                lat=msg["lat"],
                lon=msg["lon"],
                opened_ms=t1_ms,
                resolved_ms=None,
                acked_ms=None,
                trip=trip,
            )
            self._hazard[vid] = opened
            changed.append(opened)
        return changed

    def offline(self, vehicle_id: str, now_ms: int) -> Alert:
        alert = Alert(
            id=self._new_id(),
            vehicle_id=vehicle_id,
            kind="offline",
            hazard_type=None,
            severity=None,
            t0_ms=None,
            t1_ms=None,
            lat=None,
            lon=None,
            opened_ms=now_ms,
            resolved_ms=None,
            acked_ms=None,
            trip=None,
        )
        self._offline[vehicle_id] = alert
        return alert

    def online(self, vehicle_id: str, now_ms: int) -> Alert | None:
        alert = self._offline.pop(vehicle_id, None)
        return replace(alert, resolved_ms=now_ms) if alert else None

    def ack(self, alert: Alert, now_ms: int) -> Alert:
        if alert.acked_ms is not None:
            return alert
        acked = replace(alert, acked_ms=now_ms)
        for book in (self._hazard, self._offline):
            if book.get(alert.vehicle_id, None) and book[alert.vehicle_id].id == alert.id:
                book[alert.vehicle_id] = acked
        return acked
