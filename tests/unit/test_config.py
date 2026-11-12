from pathlib import Path

import pytest
import yaml

from fleet.config import ConfigError, load_config

DEFAULT = Path(__file__).resolve().parents[2] / "config" / "fleet.yaml"


def test_req001_default_fleet_matches_brief():
    cfg = load_config(DEFAULT)

    vans = [(v.id, v.name, v.route.id, v.route.name, v.route.speed_limit_kmh) for v in cfg.vehicles]
    assert vans == [
        ("veh-01", "Van 01", "A", "North (Taunton Rd)", 60),
        ("veh-02", "Van 02", "B", "Downtown (King St)", 50),
        ("veh-03", "Van 03", "C", "East (Harmony Rd)", 70),
    ]


def test_req001_default_thresholds_match_brief():
    t = load_config(DEFAULT).thresholds

    assert (
        t.brake_high_ms2,
        t.brake_critical_ms2,
        t.traction_min_speed_kmh,
        t.coolant_high_c,
        t.soc_warning_pct,
        t.soc_high_pct,
        t.overspeed_margin_kmh,
    ) == (4.0, 7.0, 20.0, 90.0, 20.0, 10.0, 10.0)


def _mutated(tmp_path: Path, mutate) -> Path:
    raw = yaml.safe_load(DEFAULT.read_text())
    mutate(raw)
    path = tmp_path / "fleet.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


def test_req001_missing_field_is_named(tmp_path):
    path = _mutated(tmp_path, lambda raw: raw["vehicles"][1].pop("route"))

    with pytest.raises(ConfigError, match=r"vehicles\[1\]\.route: missing"):
        load_config(path)


def test_req001_unknown_route_is_named(tmp_path):
    path = _mutated(tmp_path, lambda raw: raw["vehicles"][2].update(route="Z"))

    with pytest.raises(ConfigError, match=r"vehicles\[2\]\.route: unknown route 'Z'"):
        load_config(path)


def test_req001_duplicate_vehicle_id_is_named(tmp_path):
    path = _mutated(tmp_path, lambda raw: raw["vehicles"][1].update(id="veh-01"))

    with pytest.raises(ConfigError, match=r"vehicles\[1\]\.id: duplicate id 'veh-01'"):
        load_config(path)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda raw: raw["routes"]["B"].update(speed_limit_kmh="fast"),
            r"routes\.B\.speed_limit_kmh",
        ),
        (lambda raw: raw["demo"].update(port=True), r"demo\.port"),
        (lambda raw: raw["publisher"].update(buffer_size=60.5), r"publisher\.buffer_size"),
    ],
)
def test_req001_wrong_type_is_named(tmp_path, mutate, message):
    path = _mutated(tmp_path, mutate)

    with pytest.raises(ConfigError, match=message + ": expected"):
        load_config(path)


def test_req001_default_runtime_settings_match_spec():
    cfg = load_config(DEFAULT)

    assert (cfg.demo.port, cfg.demo.time_scale, cfg.demo.seed) == (8000, 10.0, 42)
    assert cfg.cloud.offline_timeout_s == 10.0
    assert (cfg.publisher.telemetry_hz, cfg.publisher.buffer_size) == (1.0, 60)
    assert (cfg.charging.start_at_pct, cfg.charging.stop_at_pct) == (10.0, 90.0)
    assert all(len(r.anchors) >= 2 for r in cfg.routes.values())


@pytest.mark.parametrize(
    "tie_break",
    [
        ["traction_loss", "harsh_braking", "overheat", "low_energy"],
        ["traction_loss", "harsh_braking", "overheat", "low_energy", "overspeed", "overspeed"],
        ["traction_loss", "harsh_braking", "overheat", "low_energy", "pothole"],
    ],
    ids=["missing", "duplicate", "unknown"],
)
def test_req021_tie_break_must_list_each_hazard_once(tmp_path, tie_break):
    path = _mutated(tmp_path, lambda raw: raw["thresholds"].update(tie_break=tie_break))

    with pytest.raises(
        ConfigError, match=r"thresholds\.tie_break: must list each hazard type once"
    ):
        load_config(path)
