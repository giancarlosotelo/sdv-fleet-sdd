from pathlib import Path

import yaml

from fleet.vehicle import signals

OVERLAY = Path(__file__).resolve().parents[2] / "vss" / "overlay.vspec"


def test_req040_every_custom_signal_is_in_the_overlay():
    overlay = yaml.safe_load(OVERLAY.read_text())

    assert signals.CUSTOM and all(p in overlay for p in signals.CUSTOM)
    assert not any(p.startswith("Vehicle.Fleet.") for p in signals.STANDARD)


def test_req040_overlay_json_is_generated_from_vspec(tmp_path):
    """Fails when overlay.vspec changes: re-run scripts/overlay_to_json.py."""
    import subprocess
    import sys

    out = tmp_path / "overlay.json"
    subprocess.run(
        [sys.executable, "scripts/overlay_to_json.py", str(out)], check=True, cwd=OVERLAY.parents[1]
    )

    assert out.read_text() == (OVERLAY.parent / "overlay.json").read_text()
