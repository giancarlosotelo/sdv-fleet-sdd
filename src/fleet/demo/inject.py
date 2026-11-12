from dataclasses import dataclass

from fleet.demo.wiring import Demo
from fleet.vehicle import signals

INJECTED_DECEL_MS2 = 7.5


@dataclass(frozen=True)
class Injection:
    vehicle_id: str
    at_ms: int


async def _wait_until_not_critical(demo: Demo, vehicle_id: str, timeout_s: float = 5.0) -> None:
    """A critical hazard already in place would mask the injected one (same severity, no change)."""
    twin, waited = demo.twins[vehicle_id], 0.0
    while waited < timeout_s:
        if (await twin.get([signals.HAZARD_SEVERITY]))[signals.HAZARD_SEVERITY] < 3:
            return
        await demo.clock.sleep(0.01)
        waited += 0.01


async def inject_hazards(demo: Demo, n: int, spacing_s: float = 0.3) -> list[Injection]:
    """Writes n hard decelerations into the vans' twins, round-robin (spec REQ-121)."""
    vehicles, injections = list(demo.twins), []
    for i in range(n):
        vid = vehicles[i % len(vehicles)]
        await _wait_until_not_critical(demo, vid)
        injections.append(Injection(vid, demo.clock.now_ms()))
        await demo.twins[vid].set({signals.ACCEL: -INJECTED_DECEL_MS2})
        await demo.clock.sleep(spacing_s)
    return injections
