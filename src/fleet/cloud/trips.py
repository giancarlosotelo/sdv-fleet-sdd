from dataclasses import dataclass, field
from typing import Any

from fleet.cloud.analytics import energy_used_kwh, hazards_per_100km
from fleet.cloud.storage import Trip


@dataclass
class _Open:
    trip: int
    start_odometer_km: float
    socs: list[float] = field(default_factory=list)
    hazards: int = 0
    complete: bool = True


class TripTracker:
    """Builds trip results from telemetry (spec REQ-085).

    A van's first observed trip only counts if it was seen from its start (trip 1 at odometer ~0).
    """

    def __init__(self, pack_kwh: dict[str, float], route: dict[str, str]):
        self._pack, self._route = pack_kwh, route
        self._open: dict[str, _Open] = {}

    def current_trip(self, vehicle_id: str) -> int | None:
        current = self._open.get(vehicle_id)
        return current.trip if current else None

    def hazard_opened(self, vehicle_id: str) -> None:
        if vehicle_id in self._open:
            self._open[vehicle_id].hazards += 1

    def telemetry(self, msg: dict[str, Any], now_ms: int) -> Trip | None:
        vid, trip, odo, soc = msg["vehicle_id"], msg["trip"], msg["odometer_km"], msg["soc_pct"]
        current = self._open.get(vid)
        if current is None:
            seen_from_start = trip == 1 and odo < 0.1
            self._open[vid] = _Open(trip, odo, [soc], complete=seen_from_start)
            return None
        current.socs.append(soc)
        if trip <= current.trip:
            return None
        self._open[vid] = _Open(trip, odo, [soc])
        if not current.complete:
            return None
        distance = odo - current.start_odometer_km
        return Trip(
            vehicle_id=vid,
            route_id=self._route[vid],
            trip=current.trip,
            distance_km=distance,
            energy_kwh=energy_used_kwh(current.socs, self._pack[vid]),
            hazards=current.hazards,
            hazards_per_100km=hazards_per_100km(current.hazards, distance),
            completed_ms=now_ms,
        )
