#!/usr/bin/env python3
"""Find functions/classes defined in production code but only referenced in test files.

Neither vulture nor deadcode handles this case: vulture treats all files equally
(no prod vs test distinction), and deadcode crashes on Python 3.14 (uses removed ast.Str).
"""

import ast
import sys
from pathlib import Path


def _is_test_file(path: Path) -> bool:
    parts = str(path)
    return "/tests/" in parts or path.name.startswith("test_") or path.name == "conftest.py"


def _get_top_level_definitions(src: Path) -> dict[str, list[str]]:
    """Return {name: [file:line, ...]} for all top-level def/class in production code."""
    defs: dict[str, list[str]] = {}
    for py_file in sorted(src.rglob("*.py")):
        if _is_test_file(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    defs.setdefault(node.name, []).append(f"{py_file.relative_to(src)}:{node.lineno}")
    return defs


def _collect_references(src: Path, *, test_files: bool) -> set[str]:
    """Return all names referenced in production files or test files.

    When test_files=True, collect from test files only.
    When test_files=False, collect from production files only.
    """
    refs: set[str] = set()
    for py_file in src.rglob("*.py"):
        is_test = _is_test_file(py_file)
        if test_files and not is_test:
            continue
        if not test_files and is_test:
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                refs.add(node.id)
            elif isinstance(node, ast.Attribute):
                refs.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    refs.add(alias.name if alias.asname is None else alias.asname)
    return refs


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "src")
    defs = _get_top_level_definitions(src)
    prod_refs = _collect_references(src, test_files=False)
    test_refs = _collect_references(src, test_files=True)

    dead: list[tuple[str, str]] = []
    for name, locations in sorted(defs.items()):
        if name not in prod_refs and name in test_refs:
            for loc in locations:
                dead.append((loc, name))

    if not dead:
        return 0

    print("Production code only referenced from tests (dead code):")
    for loc, name in dead:
        print(f"  {loc}: {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
