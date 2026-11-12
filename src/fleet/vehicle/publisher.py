import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

from contracts import hazard_key, telemetry_key
from fleet.clock import Clock
from fleet.transport.outbox import Outbox
from fleet.transport.zenoh import Zenoh
from fleet.vehicle import signals
from fleet.vehicle.twin import Twin, TwinUnavailable

log = logging.getLogger(__name__)
TELEMETRY_SIGNALS = list(signals.STANDARD + (signals.TRIP, signals.SIM_TIME))
HAZARD_SIGNALS = [signals.HAZARD_TYPE, signals.HAZARD_SEVERITY, signals.HAZARD_T0]
POSITION = [signals.LAT, signals.LON, signals.SIM_TIME]


class Publisher:
    """Twin -> Zenoh: telemetry at a fixed wall-clock rate, hazards the moment they change (REQ-072)."""

    def __init__(
        self,
        vehicle_id: str,
        twin: Twin,
        zenoh: Zenoh,
        clock: Clock,
        telemetry_hz: float,
        buffer_size: int,
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ):
        self._vid, self._twin, self._clock, self._hz, self._new_id = (
            vehicle_id,
            twin,
            clock,
            telemetry_hz,
            new_id,
        )
        self.outbox = Outbox(zenoh.put, clock, buffer_size)
        self._tasks: list[asyncio.Task] = []
        self._hazard: dict[str, Any] = {}

    async def start(self) -> None:
        self._tasks.append(asyncio.create_task(self.outbox.run()))
        await self._twin.subscribe(HAZARD_SIGNALS, self._on_hazard)

    def run_in_background(self) -> None:
        self._tasks.append(asyncio.create_task(self.run_telemetry()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()

    def _envelope(self, kind: str, sim_ts: float) -> dict[str, Any]:
        return {
            "kind": kind,
            "schema_version": 1,
            "msg_id": self._new_id(),
            "vehicle_id": self._vid,
            "sim_ts": sim_ts,
            "wall_ts": self._clock.now_ms(),
        }

    async def _on_hazard(self, values: dict[str, Any]) -> None:
        # The detector sets type, severity, T0 in one write and the databroker notifies them one by
        # one in that order; build the message from notified values, since a get() may already see
        # the next change when a hazard lasts a single tick.
        self._hazard.update(values)
        if signals.HAZARD_T0 not in values:
            return
        try:
            pos = await self._twin.get(POSITION)
        except TwinUnavailable as ex:  # log and keep running (REQ-074)
            log.warning("veh %s: can't read position for hazard: %s", self._vid, ex)
            pos = dict.fromkeys(POSITION)
        msg = self._envelope("hazard", pos[signals.SIM_TIME] or 0.0) | {
            "hazard_type": self._hazard[signals.HAZARD_TYPE],
            "severity": self._hazard[signals.HAZARD_SEVERITY],
            "t0": self._hazard[signals.HAZARD_T0],
            "lat": pos[signals.LAT] or 0.0,
            "lon": pos[signals.LON] or 0.0,
        }
        key = hazard_key(self._vid)
        await self.outbox.submit(key, json.dumps(msg).encode(), latest_key=key)

    async def _publish_telemetry(self) -> None:
        try:
            v = await self._twin.get(TELEMETRY_SIGNALS)
        except TwinUnavailable as ex:  # log and keep running (REQ-074)
            log.warning("veh %s: can't read telemetry: %s", self._vid, ex)
            return
        if None in v.values():
            return
        msg = self._envelope("telemetry", v[signals.SIM_TIME]) | {
            "lat": v[signals.LAT],
            "lon": v[signals.LON],
            "speed_kmh": v[signals.SPEED],
            "accel_ms2": v[signals.ACCEL],
            "traction_active": v[signals.TRACTION],
            "soc_pct": v[signals.SOC],
            "coolant_c": v[signals.COOLANT],
            "odometer_km": v[signals.ODOMETER],
            "trip": v[signals.TRIP],
        }
        await self.outbox.submit(telemetry_key(self._vid), json.dumps(msg).encode())

    async def run_telemetry(self, ticks: int | None = None) -> None:
        done = 0
        while ticks is None or done < ticks:
            await self._publish_telemetry()
            await self._clock.sleep(1 / self._hz)
            done += 1
