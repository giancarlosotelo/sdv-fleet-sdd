import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ_HEADING = re.compile(r"^\*\*REQ-(\d{3})(?P<v2> \[V2\])?", re.MULTILINE)
REQ_IN_TEST = re.compile(r"req[_-]?(\d{3})", re.IGNORECASE)


def _v1_requirements() -> set[str]:
    spec = (ROOT / "specs" / "fleet-monitor.md").read_text()
    return {m.group(1) for m in REQ_HEADING.finditer(spec) if not m.group("v2")}


def _referenced_in_tests() -> set[str]:
    found = set()
    for path in (ROOT / "tests").rglob("test_*.py"):
        if path.name != "test_traceability.py":
            found |= set(REQ_IN_TEST.findall(path.read_text()))
    return found


def test_every_v1_requirement_has_a_test():
    """Spec §10 item 6: every untagged REQ maps to at least one test."""
    v1 = _v1_requirements()

    assert len(v1) == 43
    assert sorted(v1 - _referenced_in_tests()) == []
