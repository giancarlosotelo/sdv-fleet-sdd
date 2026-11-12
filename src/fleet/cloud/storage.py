import json
import sqlite3
from dataclasses import astuple, dataclass, fields
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Alert:
    id: str
    vehicle_id: str
    kind: str  # "hazard" or "offline"
    hazard_type: str | None
    severity: int | None
    t0_ms: int | None
    t1_ms: int | None
    lat: float | None
    lon: float | None
    opened_ms: int
    resolved_ms: int | None
    acked_ms: int | None
    trip: int | None


@dataclass(frozen=True)
class Trip:
    vehicle_id: str
    route_id: str
    trip: int
    distance_km: float
    energy_kwh: float
    hazards: int
    hazards_per_100km: float | None
    completed_ms: int


class Storage(Protocol):
    def add_telemetry(
        self, msg: dict[str, Any], vehicle_name: str | None = None, route_id: str | None = None
    ) -> None: ...
    def telemetry(self) -> list[dict[str, Any]]: ...
    def add_quarantine(self, raw: bytes, reason: str, received_ms: int) -> None: ...
    def quarantine(self) -> list[tuple[bytes, str, int]]: ...
    def save_alert(self, alert: Alert) -> None: ...
    def alerts(self, include_resolved: bool = False) -> list[Alert]: ...
    def add_trip(self, trip: Trip) -> None: ...
    def trips(self, vehicle_id: str | None = None) -> list[Trip]: ...


_ALERT_COLS = [f.name for f in fields(Alert)]
_TRIP_COLS = [f.name for f in fields(Trip)]


class SqliteStorage:
    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS telemetry (
                seq INTEGER PRIMARY KEY, msg TEXT NOT NULL, vehicle_name TEXT, route_id TEXT);
            CREATE TABLE IF NOT EXISTS quarantine (
                seq INTEGER PRIMARY KEY, raw BLOB NOT NULL, reason TEXT NOT NULL,
                received_ms INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS alerts ({", ".join(_ALERT_COLS)}, PRIMARY KEY (id));
            CREATE TABLE IF NOT EXISTS trips (seq INTEGER PRIMARY KEY, {", ".join(_TRIP_COLS)});
            """
        )

    def close(self) -> None:
        self._db.close()

    def add_telemetry(
        self, msg: dict[str, Any], vehicle_name: str | None = None, route_id: str | None = None
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO telemetry (msg, vehicle_name, route_id) VALUES (?, ?, ?)",
                (json.dumps(msg), vehicle_name, route_id),
            )

    def telemetry(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT msg, vehicle_name, route_id FROM telemetry ORDER BY seq")
        return [{**json.loads(m), "vehicle_name": n, "route_id": r} for m, n, r in rows]

    def add_quarantine(self, raw: bytes, reason: str, received_ms: int) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO quarantine (raw, reason, received_ms) VALUES (?, ?, ?)",
                (raw, reason, received_ms),
            )

    def quarantine(self) -> list[tuple[bytes, str, int]]:
        rows = self._db.execute("SELECT raw, reason, received_ms FROM quarantine ORDER BY seq")
        return [tuple(r) for r in rows]

    def save_alert(self, alert: Alert) -> None:
        marks = ", ".join("?" for _ in _ALERT_COLS)
        with self._db:
            self._db.execute(
                f"INSERT OR REPLACE INTO alerts ({', '.join(_ALERT_COLS)}) VALUES ({marks})",
                astuple(alert),
            )

    def alerts(self, include_resolved: bool = False) -> list[Alert]:
        where = "" if include_resolved else "WHERE resolved_ms IS NULL"
        rows = self._db.execute(
            f"SELECT {', '.join(_ALERT_COLS)} FROM alerts {where} ORDER BY opened_ms DESC, rowid DESC"
        )
        return [Alert(*r) for r in rows]

    def add_trip(self, trip: Trip) -> None:
        marks = ", ".join("?" for _ in _TRIP_COLS)
        with self._db:
            self._db.execute(
                f"INSERT INTO trips ({', '.join(_TRIP_COLS)}) VALUES ({marks})", astuple(trip)
            )

    def trips(self, vehicle_id: str | None = None) -> list[Trip]:
        sql = f"SELECT {', '.join(_TRIP_COLS)} FROM trips"
        args: tuple = ()
        if vehicle_id:
            sql, args = sql + " WHERE vehicle_id = ?", (vehicle_id,)
        return [Trip(*r) for r in self._db.execute(sql + " ORDER BY seq", args)]
