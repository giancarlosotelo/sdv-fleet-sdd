from collections import OrderedDict
from collections.abc import Iterable
from typing import Final

from contracts import Invalid, Valid, validate

DUPLICATE: Final = "duplicate"


class Ingest:
    """Validates, drops unknown vans and ignores repeated msg_ids (spec REQ-080)."""

    def __init__(self, known_vehicles: Iterable[str], dedupe_window: int = 100_000):
        self._known = set(known_vehicles)
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._window = dedupe_window
        self.rejected = 0

    def check(self, raw: bytes) -> Valid | Invalid | str:
        result = validate(raw)
        if isinstance(result, Valid) and result.msg["vehicle_id"] not in self._known:
            result = Invalid(f"vehicle_id: unknown vehicle {result.msg['vehicle_id']!r}")
        if isinstance(result, Invalid):
            self.rejected += 1
            return result
        msg_id = result.msg["msg_id"]
        if msg_id in self._seen:
            return DUPLICATE
        self._seen[msg_id] = None
        if len(self._seen) > self._window:
            self._seen.popitem(last=False)
        return result
