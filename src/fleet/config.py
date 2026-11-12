from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


# Mirrors fleet.vehicle.rules.HazardType; config is shared, so it can't import vehicle code.
HAZARD_TYPES = ("harsh_braking", "traction_loss", "overheat", "low_energy", "overspeed")


@dataclass(frozen=True)
class Profile:
    stops_per_km: float
    harsh_brake_share: float
    traction_events_per_km: float
    speeding_tendency: float


@dataclass(frozen=True)
class Route:
    id: str
    name: str
    speed_limit_kmh: float
    anchors: tuple[tuple[float, float], ...]
    profile: Profile


@dataclass(frozen=True)
class Vehicle:
    id: str
    name: str
    route: Route
    pack_kwh: float
    start_soc_pct: float


@dataclass(frozen=True)
class Thresholds:
    brake_high_ms2: float
    brake_critical_ms2: float
    traction_min_speed_kmh: float
    coolant_high_c: float
    soc_warning_pct: float
    soc_high_pct: float
    overspeed_margin_kmh: float
    tie_break: tuple[str, ...]


@dataclass(frozen=True)
class Charging:
    start_at_pct: float
    stop_at_pct: float
    rate_kw: float


@dataclass(frozen=True)
class Publisher:
    telemetry_hz: float
    buffer_size: int


@dataclass(frozen=True)
class Cloud:
    offline_timeout_s: float


@dataclass(frozen=True)
class Demo:
    port: int
    time_scale: float
    seed: int


@dataclass(frozen=True)
class FleetConfig:
    vehicles: tuple[Vehicle, ...]
    routes: dict[str, Route]
    thresholds: Thresholds
    charging: Charging
    publisher: Publisher
    cloud: Cloud
    demo: Demo


def _get(raw: Any, key: str, path: str) -> Any:
    if not isinstance(raw, dict):
        raise ConfigError(f"{path or '<root>'}: expected a mapping")
    if key not in raw:
        raise ConfigError(f"{_join(path, key)}: missing")
    return raw[key]


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _number(value: Any, kind: type, path: str) -> Any:
    accepted = (int,) if kind is int else (int, float)
    if isinstance(value, bool) or not isinstance(value, accepted):
        raise ConfigError(f"{path}: expected {kind.__name__}, got {value!r}")
    return kind(value)


def _flat(cls: type, raw: Any, path: str) -> Any:
    """Build a dataclass of numbers, strings and string tuples from a mapping."""
    values = {}
    for f in fields(cls):
        value, fpath = _get(raw, f.name, path), _join(path, f.name)
        if f.type in (int, float):
            values[f.name] = _number(value, f.type, fpath)
        elif f.type is str:
            values[f.name] = str(value)
        else:
            values[f.name] = tuple(str(v) for v in value)
    return cls(**values)


def _route(rid: str, raw: Any, path: str) -> Route:
    anchors = tuple(
        (_number(a[0], float, f"{path}.anchors[{i}]"), _number(a[1], float, f"{path}.anchors[{i}]"))
        for i, a in enumerate(_get(raw, "anchors", path))
    )
    return Route(
        id=rid,
        name=str(_get(raw, "name", path)),
        speed_limit_kmh=_number(
            _get(raw, "speed_limit_kmh", path), float, f"{path}.speed_limit_kmh"
        ),
        anchors=anchors,
        profile=_flat(Profile, _get(raw, "profile", path), f"{path}.profile"),
    )


def _vehicle(raw: Any, path: str, routes: dict[str, Route]) -> Vehicle:
    route_id = _get(raw, "route", path)
    if route_id not in routes:
        raise ConfigError(f"{path}.route: unknown route {route_id!r}")
    return Vehicle(
        id=str(_get(raw, "id", path)),
        name=str(_get(raw, "name", path)),
        route=routes[route_id],
        pack_kwh=_number(_get(raw, "pack_kwh", path), float, f"{path}.pack_kwh"),
        start_soc_pct=_number(_get(raw, "start_soc_pct", path), float, f"{path}.start_soc_pct"),
    )


def _thresholds(raw: Any) -> Thresholds:
    t = _flat(Thresholds, raw, "thresholds")
    if sorted(t.tie_break) != sorted(HAZARD_TYPES):
        raise ConfigError(
            f"thresholds.tie_break: must list each hazard type once {HAZARD_TYPES}, got {t.tie_break}"
        )
    return t


def load_config(path: Path) -> FleetConfig:
    raw = yaml.safe_load(Path(path).read_text())
    routes = {rid: _route(rid, r, f"routes.{rid}") for rid, r in _get(raw, "routes", "").items()}
    vehicles = tuple(
        _vehicle(v, f"vehicles[{i}]", routes) for i, v in enumerate(_get(raw, "vehicles", ""))
    )
    seen = set()
    for i, v in enumerate(vehicles):
        if v.id in seen:
            raise ConfigError(f"vehicles[{i}].id: duplicate id {v.id!r}")
        seen.add(v.id)
    return FleetConfig(
        vehicles=vehicles,
        routes=routes,
        thresholds=_thresholds(_get(raw, "thresholds", "")),
        charging=_flat(Charging, _get(raw, "charging", ""), "charging"),
        publisher=_flat(Publisher, _get(raw, "publisher", ""), "publisher"),
        cloud=_flat(Cloud, _get(raw, "cloud", ""), "cloud"),
        demo=_flat(Demo, _get(raw, "demo", ""), "demo"),
    )
