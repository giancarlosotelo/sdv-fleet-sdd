"""Convert vss/overlay.vspec (flat VSS YAML) into the nested JSON the Kuksa Databroker loads."""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def to_tree(flat: dict) -> dict:
    tree: dict = {}
    for path, node in flat.items():
        *parents, leaf = path.split(".")
        level = tree
        for name in parents:
            level = level.setdefault(name, {"type": "branch", "description": name, "children": {}})[
                "children"
            ]
        entry = level.setdefault(leaf, {})
        entry.update(node)
        if node.get("type") == "branch":
            entry.setdefault("children", {})
    return tree


def main(out: Path = ROOT / "vss" / "overlay.json") -> None:
    flat = yaml.safe_load((ROOT / "vss" / "overlay.vspec").read_text())
    out.write_text(json.dumps(to_tree(flat), indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "vss" / "overlay.json")
