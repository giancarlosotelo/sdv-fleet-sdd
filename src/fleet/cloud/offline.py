from collections.abc import Iterable


class OfflineMonitor:
    """Wall-clock silence detection (spec REQ-083). A van never heard from counts from start-up."""

    def __init__(
        self,
        vehicles: Iterable[str],
        timeout_s: float,
        now_ms: int,
        offline: Iterable[str] = (),
    ):
        self._timeout_ms = timeout_s * 1000
        self._last = {vid: now_ms for vid in vehicles}
        self._offline: set[str] = set(offline)

    def seen(self, vehicle_id: str, now_ms: int) -> bool:
        """Records telemetry; True if the van was offline and is now back."""
        self._last[vehicle_id] = now_ms
        if vehicle_id in self._offline:
            self._offline.discard(vehicle_id)
            return True
        return False

    def check(self, now_ms: int) -> list[str]:
        """Vans that just went offline."""
        newly = [
            vid
            for vid, last in self._last.items()
            if vid not in self._offline and now_ms - last > self._timeout_ms
        ]
        self._offline.update(newly)
        return newly

    def is_online(self, vehicle_id: str) -> bool:
        return vehicle_id not in self._offline
