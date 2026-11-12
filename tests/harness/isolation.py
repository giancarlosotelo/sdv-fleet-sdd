import ast
from dataclasses import dataclass
from pathlib import Path

VEHICLE = ("fleet.vehicle",)
CLOUD = ("fleet.cloud", "fleet.pipeline", "fleet.dashboard")


@dataclass(frozen=True)
class Violation:
    file: Path
    imported: str


def _under(module: str, packages: tuple[str, ...]) -> bool:
    return any(module == p or module.startswith(p + ".") for p in packages)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
            found += [f"{node.module}.{alias.name}" for alias in node.names]
    return found


def check_isolation(src_root: Path) -> list[Violation]:
    """Vehicle and cloud packages under src_root must not import each other."""
    violations = []
    for path in sorted(src_root.rglob("*.py")):
        module = ".".join(path.relative_to(src_root).with_suffix("").parts)
        if _under(module, VEHICLE):
            forbidden = CLOUD
        elif _under(module, CLOUD):
            forbidden = VEHICLE
        else:
            continue
        flagged: list[str] = []
        for m in _imports(path):  # "from a.b import c" yields a.b and a.b.c; report it once
            if _under(m, forbidden) and not any(_under(m, (f,)) for f in flagged):
                flagged.append(m)
        violations += [Violation(path, m) for m in flagged]
    return violations
