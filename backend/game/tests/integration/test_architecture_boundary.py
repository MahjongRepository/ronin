"""Architectural boundary tests enforcing layer dependency rules.

Layer dependency direction (allowed):
  server → messaging → logic
  server → session → logic
  session → messaging (for wire message types)
  replay → logic

Forbidden (runtime imports):
  logic → replay
  messaging → session
"""

import ast
from pathlib import Path

_GAME_ROOT = Path(__file__).resolve().parents[2]


def _collect_runtime_import_targets(source_dir: Path) -> list[tuple[str, int, str]]:
    """Parse all .py files and return (filename, lineno, module) for runtime imports.

    Skip imports inside `if TYPE_CHECKING:` blocks — those are type-only
    and do not create runtime layer coupling.
    """
    results: list[tuple[str, int, str]] = []
    for py_file in source_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        type_checking_ranges = _find_type_checking_ranges(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if any(start <= node.lineno <= end for start, end in type_checking_ranges):
                continue
            if isinstance(node, ast.Import):
                results.extend((py_file.name, node.lineno, alias.name) for alias in node.names)
            elif node.module is not None:
                results.append((py_file.name, node.lineno, node.module))
    return results


def _find_type_checking_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    """Find line ranges of `if TYPE_CHECKING:` blocks."""
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            start = node.lineno
            end = max(child.lineno for child in ast.walk(node) if hasattr(child, "lineno"))
            ranges.append((start, end))
    return ranges


def test_game_logic_does_not_import_replay():
    """game.logic modules must not import from game.replay (one-way dependency)."""
    violations = [
        f"{name}:{lineno} {module}"
        for name, lineno, module in _collect_runtime_import_targets(_GAME_ROOT / "logic")
        if module.startswith("game.replay")
    ]
    assert violations == [], f"game.logic imports from game.replay: {violations}"


def test_messaging_does_not_import_session():
    """game.messaging must not import from game.session (layer boundary)."""
    violations = [
        f"{name}:{lineno} {module}"
        for name, lineno, module in _collect_runtime_import_targets(_GAME_ROOT / "messaging")
        if module.startswith("game.session")
    ]
    assert violations == [], f"game.messaging imports from game.session: {violations}"
