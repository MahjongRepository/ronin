"""Architectural boundary: game.logic must not import from game.replay."""

import ast
from pathlib import Path


def test_game_logic_does_not_import_replay():
    """game.logic modules must not import from game.replay (one-way dependency)."""
    logic_dir = Path(__file__).resolve().parents[2] / "logic"
    violations: list[str] = []

    for py_file in logic_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(
                    f"{py_file.name}:{node.lineno} import {alias.name}"
                    for alias in node.names
                    if alias.name.startswith("game.replay")
                )
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("game.replay")
            ):
                violations.append(f"{py_file.name}:{node.lineno} from {node.module}")

    assert violations == [], f"game.logic imports from game.replay: {violations}"
