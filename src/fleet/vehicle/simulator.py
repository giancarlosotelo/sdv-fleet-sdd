"""Seeded van physics along a route loop (spec REQ-030..036). step() is pure apart from the injected RNG."""

import bisect
import itertools
import math
import random
from dataclasses import dataclass

from fleet.clock import Clock
from fleet.config import Charging, Vehicle
from fleet.vehicle import signals
from fleet.vehicle.twin import Twin

CRUISE_ACCEL_MS2 = 1.5
EASE_OFF_MS2 = 1.0
TRACTION_EVENT_S = 1.5


@dataclass(frozen=True)
class VanState:
    sim_time_s: float
    lat: float
    lon: float
    speed_kmh: float
    accel_ms2: float
    traction_active: bool
    soc_pct: float
    coolant_c: float
    odometer_km: float
    trip: int


@dataclass(frozen=True)
class _Stop:
    at_m: float
    decel_ms2: float
    dwell_s: float


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


class Simulator:
    def __init__(
        self,
        van: Vehicle,
        polyline: tuple[tuple[float, float], ...],
        charging: Charging,
        rng: random.Random,
    ):
        self._van, self._poly, self._charging, self._rng = van, polyline, charging, rng
        self._cum = [0.0]
        for a, b in itertools.pairwise(polyline):
            self._cum.append(self._cum[-1] + _metres(a, b))
        self._loop_m = self._cum[-1]
        self.loop_km = self._loop_m / 1000
        self._limit_ms = van.route.speed_limit_kmh / 3.6
        self._t = 0.0
        self._s = 0.0
        self._v = 0.0
        self._accel = 0.0
        self._soc = van.start_soc_pct
        self._coolant = 60.0
        self._odometer_m = 0.0
        self._trip = 1
        self._dwell_left = 0.0
        self._traction_left = 0.0
        self._charging_now = False
        self._needs_charge = False
        self._plan_trip()

    def _plan_trip(self) -> None:
        p, rng = self._van.route.profile, self._rng
        self._stops: list[_Stop] = []
        at = rng.expovariate(p.stops_per_km / 1000) if p.stops_per_km else math.inf
        while at < self._loop_m - 50:
            harsh = rng.random() < p.harsh_brake_share
            decel = rng.uniform(4.3, 8.0) if harsh else rng.uniform(1.5, 3.0)
            self._stops.append(_Stop(at, decel, rng.uniform(5, 20)))
            at += rng.expovariate(p.stops_per_km / 1000)
        bounds = [0.0] + [s.at_m for s in self._stops] + [self._loop_m]
        self._targets = []
        for start in bounds[:-1]:
            if rng.random() < p.speeding_tendency:
                target = self._limit_ms + rng.uniform(11, 16) / 3.6
            else:
                target = self._limit_ms * rng.uniform(0.85, 0.98)
            self._targets.append((start, target))
        self._traction_at = []
        at = (
            rng.expovariate(p.traction_events_per_km / 1000)
            if p.traction_events_per_km
            else math.inf
        )
        while at < self._loop_m:
            self._traction_at.append(at)
            at += rng.expovariate(p.traction_events_per_km / 1000)
        self._braking = False

    def _next_stop(self) -> _Stop | None:
        ahead = [s for s in self._stops if s.at_m > self._s]
        if self._needs_charge:
            ahead.append(_Stop(self._loop_m, 2.0, 0.0))
        return ahead[0] if ahead else None

    def _target_ms(self) -> float:
        starts = [start for start, _ in self._targets]
        return self._targets[bisect.bisect_right(starts, self._s) - 1][1]

    def _position(self) -> tuple[float, float]:
        i = min(bisect.bisect_right(self._cum, self._s) - 1, len(self._poly) - 2)
        seg = self._cum[i + 1] - self._cum[i]
        f = (self._s - self._cum[i]) / seg if seg else 0.0
        (lat1, lon1), (lat2, lon2) = self._poly[i], self._poly[i + 1]
        return lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1)

    def _state(self) -> VanState:
        lat, lon = self._position()
        return VanState(
            sim_time_s=round(self._t, 6),
            lat=lat,
            lon=lon,
            speed_kmh=self._v * 3.6,
            accel_ms2=self._accel,
            traction_active=self._traction_left > 0,
            soc_pct=self._soc,
            coolant_c=self._coolant,
            odometer_km=self._odometer_m / 1000,
            trip=self._trip,
        )

    def step(self, dt: float) -> VanState:
        self._t += dt
        if self._charging_now:
            self._charge(dt)
        elif self._dwell_left > 0:
            self._dwell_left -= dt
            self._v, self._accel = 0.0, 0.0
            self._drain(0.0, dt)
        else:
            self._drive(dt)
        self._traction_left = max(self._traction_left - dt, 0.0)
        target_c = 55 + 0.45 * self._v * 3.6 + 3 * max(self._accel, 0.0)
        self._coolant += (target_c - self._coolant) * min(dt / 60, 1.0)
        return self._state()

    def _charge(self, dt: float) -> None:
        self._v, self._accel = 0.0, 0.0
        self._soc += self._charging.rate_kw * dt / 3600 / self._van.pack_kwh * 100
        if self._soc >= self._charging.stop_at_pct:
            self._soc = self._charging.stop_at_pct
            self._charging_now = self._needs_charge = False
            self._plan_trip()

    def _drive(self, dt: float) -> None:
        stop = self._next_stop()
        v = self._v
        if stop and (self._braking or stop.at_m - self._s <= v * v / (2 * stop.decel_ms2) + v * dt):
            self._braking = True
            v_new = max(v - stop.decel_ms2 * dt, 0.0)
            ds = (v + v_new) / 2 * dt
            self._accel = -stop.decel_ms2
            if self._s + ds >= stop.at_m or v_new == 0.0:
                ds = max(stop.at_m - self._s, 0.0)
                v_new = 0.0
                self._braking = False
                self._dwell_left = stop.dwell_s
        else:
            target = self._target_ms()
            if v < target:
                v_new = min(v + CRUISE_ACCEL_MS2 * dt, target)
            else:
                v_new = max(v - EASE_OFF_MS2 * dt, target)
            ds = (v + v_new) / 2 * dt
            self._accel = (v_new - v) / dt
        crossed = [a for a in self._traction_at if self._s < a <= self._s + ds]
        if crossed:
            self._traction_left = TRACTION_EVENT_S
        self._v = v_new
        self._s += ds
        self._odometer_m += ds
        self._drain(ds, dt)
        if self._soc <= self._charging.start_at_pct:
            self._needs_charge = True
        if self._s >= self._loop_m - 1e-6:
            self._s = max(self._s - self._loop_m, 0.0)
            self._trip += 1
            if self._needs_charge:
                self._s, self._v, self._accel = 0.0, 0.0, 0.0
                self._dwell_left = 0.0
                self._charging_now = True
            else:
                self._plan_trip()

    def _drain(self, ds_m: float, dt: float) -> None:
        km = ds_m / 1000
        kwh = km * (0.15 + 0.0015 * self._v * 3.6) + max(self._accel, 0.0) * km * 0.05
        kwh += 0.3 * dt / 3600  # auxiliary load, kW
        self._soc = max(self._soc - kwh / self._van.pack_kwh * 100, 0.0)


def state_to_signals(state: VanState) -> dict[str, object]:
    return {
        signals.LAT: state.lat,
        signals.LON: state.lon,
        signals.SPEED: state.speed_kmh,
        signals.ACCEL: state.accel_ms2,
        signals.TRACTION: state.traction_active,
        signals.SOC: state.soc_pct,
        signals.COOLANT: state.coolant_c,
        signals.ODOMETER: state.odometer_km,
        signals.TRIP: state.trip,
        signals.SIM_TIME: state.sim_time_s,
    }


async def run_simulator(
    sim: Simulator,
    twin: Twin,
    clock: Clock,
    time_scale: float,
    dt_s: float = 0.1,
    ticks: int | None = None,
) -> None:
    """Step in sim time, paced to a wall-clock deadline of dt / time_scale per tick (REQ-032).

    Pacing by deadline keeps slow twin writes (a real databroker) from stretching sim time.
    """
    done, deadline_ms = 0, clock.now_ms()
    while ticks is None or done < ticks:
        await twin.set(state_to_signals(sim.step(dt_s)))
        deadline_ms += dt_s / time_scale * 1000
        await clock.sleep(max(deadline_ms - clock.now_ms(), 0) / 1000)
        done += 1
