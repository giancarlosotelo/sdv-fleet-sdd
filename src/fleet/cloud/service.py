import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from contracts import HAZARD_TOPIC, TELEMETRY_TOPIC, Invalid
from fleet.clock import Clock
from fleet.cloud.alerts import AlertBook
from fleet.cloud.analytics import LatencyStats, latency_stats
from fleet.cloud.ingest import DUPLICATE, Ingest
from fleet.cloud.offline import OfflineMonitor
from fleet.cloud.storage import Alert, Storage
from fleet.cloud.trips import TripTracker
from fleet.config import FleetConfig
from fleet.transport.pubsub import PubSub

LATENCY_TARGET_MS = 2000
Listener = Callable[[dict[str, Any]], Awaitable[None]]


class CloudService:
    """The live 2-second path: ingest, alerts, offline, latency, trips (spec REQ-080..086)."""

    def __init__(
        self,
        cfg: FleetConfig,
        storage: Storage,
        clock: Clock,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ):
        self._cfg, self._storage, self._clock = cfg, storage, clock
        self._vans = {v.id: v for v in cfg.vehicles}
        self._ingest = Ingest(self._vans)
        self._book = AlertBook(new_id, storage.alerts())
        self._offline = OfflineMonitor(
            self._vans,
            cfg.cloud.offline_timeout_s,
            clock.now_ms(),
            offline=self._book.offline_vehicles(),  # restored open offline alerts (REQ-086)
        )
        self._trips = TripTracker(
            {v.id: v.pack_kwh for v in cfg.vehicles}, {v.id: v.route.id for v in cfg.vehicles}
        )
        self._latest: dict[str, dict[str, Any]] = {}
        self._latencies: list[int] = []
        self._listeners: list[Listener] = []
        self._task: asyncio.Task | None = None

    @property
    def rejected(self) -> int:
        return self._ingest.rejected

    def listen(self, listener: Listener) -> None:
        self._listeners.append(listener)

    async def _emit(self, event: dict[str, Any]) -> None:
        for listener in self._listeners:
            await listener(event)

    async def start(self, pubsub: PubSub) -> None:
        await pubsub.subscribe(TELEMETRY_TOPIC, self.handle)
        await pubsub.subscribe(HAZARD_TOPIC, self.handle)

    def run_in_background(self) -> None:
        self._task = asyncio.create_task(self._offline_loop())

    async def _offline_loop(self) -> None:
        while True:
            await self.check_offline()
            await self._clock.sleep(1.0)

    async def handle(self, raw: bytes) -> None:
        t1_ms = self._clock.now_ms()
        result = self._ingest.check(raw)
        if result is DUPLICATE:
            return
        if isinstance(result, Invalid):
            self._storage.add_quarantine(raw, result.reason, t1_ms)
            return
        msg = result.msg
        if msg["kind"] == "telemetry":
            await self._on_telemetry(msg, t1_ms)
        else:
            await self._on_hazard(msg, t1_ms)

    async def _on_telemetry(self, msg: dict[str, Any], now_ms: int) -> None:
        vid = msg["vehicle_id"]
        if self._offline.seen(vid, now_ms):
            resolved = self._book.online(vid, now_ms)
            if resolved:
                await self._save(resolved)
        self._latest[vid] = msg
        trip = self._trips.telemetry(msg, now_ms)
        await self._emit({"type": "vehicle", "vehicle": self._vehicle_view(vid)})
        if trip:
            self._storage.add_trip(trip)
            await self._emit({"type": "route_table", "rows": self.route_table()})

    async def _on_hazard(self, msg: dict[str, Any], t1_ms: int) -> None:
        vid = msg["vehicle_id"]
        changed = self._book.hazard(msg, t1_ms, self._trips.current_trip(vid))
        for alert in changed:
            await self._save(alert)
            if alert.resolved_ms is None:
                self._trips.hazard_opened(vid)
                self._latencies.append(alert.t1_ms - alert.t0_ms)
                await self._emit({"type": "latency", "latency": self._latency_view()})

    async def _save(self, alert: Alert) -> None:
        self._storage.save_alert(alert)
        await self._emit({"type": "alert", "alert": asdict(alert)})

    async def check_offline(self) -> None:
        now = self._clock.now_ms()
        for vid in self._offline.check(now):
            await self._save(self._book.offline(vid, now))
            if vid in self._latest:
                await self._emit({"type": "vehicle", "vehicle": self._vehicle_view(vid)})

    async def ack(self, alert_id: str) -> Alert | None:
        alert = next(
            (a for a in self._storage.alerts(include_resolved=True) if a.id == alert_id), None
        )
        if alert is None:
            return None
        acked = self._book.ack(alert, self._clock.now_ms())
        if acked is not alert:
            await self._save(acked)
        return acked

    def latency(self) -> LatencyStats:
        return latency_stats(self._latencies)

    def _latency_view(self) -> dict[str, Any]:
        stats = self.latency()
        passing = stats.p95_ms is not None and stats.p95_ms < LATENCY_TARGET_MS
        return asdict(stats) | {"target_ms": LATENCY_TARGET_MS, "pass": passing}

    def _vehicle_view(self, vid: str) -> dict[str, Any]:
        van, msg = self._vans[vid], self._latest.get(vid, {})
        return {
            "id": vid,
            "name": van.name,
            "route_id": van.route.id,
            "online": self._offline.is_online(vid),
            **{
                k: msg.get(k) for k in ("lat", "lon", "speed_kmh", "soc_pct", "trip", "odometer_km")
            },
        }

    def route_table(self) -> list[dict[str, Any]]:
        rows = []
        for van in self._cfg.vehicles:
            trips = self._storage.trips(van.id)
            km = sum(t.distance_km for t in trips)
            kwh = sum(t.energy_kwh for t in trips)
            hazards = sum(t.hazards for t in trips)
            rows.append(
                {
                    "route_id": van.route.id,
                    "route_name": van.route.name,
                    "vehicle": van.name,
                    "trips": len(trips),
                    "km": km if trips else None,
                    "kwh": kwh if trips else None,
                    "kwh_per_100km": kwh / km * 100 if trips and km else None,
                    "hazards": hazards if trips else None,
                    "hazards_per_100km": hazards / km * 100 if trips and km else None,
                }
            )
        scored = [r for r in rows if r["hazards_per_100km"] is not None]
        top = max(scored, key=lambda r: r["hazards_per_100km"], default=None)
        for r in rows:
            r["highest"] = r is top
        return rows

    def alerts(self, include_resolved: bool = False) -> list[dict[str, Any]]:
        return [asdict(a) for a in self._storage.alerts(include_resolved)]

    def snapshot(self, include_resolved: bool = False) -> dict[str, Any]:
        return {
            "vehicles": {vid: self._vehicle_view(vid) for vid in self._vans},
            "alerts": self.alerts(include_resolved),
            "latency": self._latency_view(),
            "route_table": self.route_table(),
        }
