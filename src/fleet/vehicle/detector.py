import logging
from typing import Any

from fleet.clock import Clock
from fleet.config import Thresholds
from fleet.vehicle import signals
from fleet.vehicle.rules import Signals, evaluate, most_severe
from fleet.vehicle.twin import Twin, TwinUnavailable

log = logging.getLogger(__name__)


class Detector:
    """Evaluates the rules on every signal update; writes the current hazard only when it changes."""

    def __init__(self, twin: Twin, speed_limit_kmh: float, thresholds: Thresholds, clock: Clock):
        self._twin, self._limit, self._t, self._clock = twin, speed_limit_kmh, thresholds, clock
        self._latest: dict[str, Any] = {}
        self._current: tuple[str, int] | None = None

    async def start(self) -> None:
        await self._write(("none", 0))
        await self._twin.subscribe(list(signals.RULE_INPUTS), self._on_change)

    async def _on_change(self, values: dict[str, Any]) -> None:
        self._latest.update(values)
        if any(self._latest.get(p) is None for p in signals.RULE_INPUTS):
            return
        s = Signals(
            speed_kmh=self._latest[signals.SPEED],
            accel_ms2=self._latest[signals.ACCEL],
            traction_active=self._latest[signals.TRACTION],
            coolant_c=self._latest[signals.COOLANT],
            soc_pct=self._latest[signals.SOC],
        )
        top = most_severe(evaluate(s, self._limit, self._t), self._t.tie_break)
        current = (str(top.type), int(top.severity)) if top else ("none", 0)
        if current != self._current:
            await self._write(current)

    async def _write(self, current: tuple[str, int]) -> None:
        try:
            await self._twin.set(
                {
                    signals.HAZARD_TYPE: current[0],
                    signals.HAZARD_SEVERITY: current[1],
                    signals.HAZARD_T0: self._clock.now_ms(),
                }
            )
        except TwinUnavailable as ex:  # not recorded, so the next update writes it again (REQ-074)
            log.warning("can't write hazard %s: %s", current, ex)
            return
        self._current = current
