#!/usr/bin/env python3
"""Find production definitions (top-level and class methods) that are only referenced in tests or not referenced at all.

Neither vulture nor deadcode handles these cases: vulture treats all files equally
(no prod vs test distinction), and deadcode crashes on Python 3.14 (uses removed ast.Str).
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


def _is_test_file(path: Path) -> bool:
    parts = str(path)
    return "/tests/" in parts or path.name.startswith("test_") or path.name == "conftest.py"


@dataclass
class _ProductionScan:
    defs: dict[str, list[str]]
    def_refs: dict[str, "_ReferenceBucket"]
    module_refs: "_ReferenceBucket"
    method_aliases: dict[str, set[str]]
    class_methods: dict[str, set[str]]
    class_implicit_methods: dict[str, set[str]]


@dataclass
class _ReferenceBucket:
    names: set[str]
    attrs: set[str]

    def merge(self, other: "_ReferenceBucket") -> None:
        self.names.update(other.names)
        self.attrs.update(other.attrs)


@dataclass
class DeadCodeReport:
    test_only: list[tuple[str, str]]
    unreferenced: list[tuple[str, str]]

    def all_dead(self) -> list[tuple[str, str]]:
        return [*self.test_only, *self.unreferenced]


class _ReferenceCollector(ast.NodeVisitor):
    def __init__(self, class_methods: dict[str, set[str]]) -> None:
        self.module_refs = _ReferenceBucket(names=set(), attrs=set())
        self.def_refs: dict[str, _ReferenceBucket] = {}
        self._scope_stack: list[str] = []
        self._class_stack: list[str] = []
        self._class_methods = class_methods

    def _current_bucket(self) -> _ReferenceBucket:
        if not self._scope_stack:
            return self.module_refs
        return self.def_refs.setdefault(
            self._scope_stack[-1],
            _ReferenceBucket(names=set(), attrs=set()),
        )

    def _enter_definition(self, name: str) -> None:
        self._scope_stack.append(name)

    def _exit_definition(self) -> None:
        self._scope_stack.pop()

    def _add_name_reference(self, name: str) -> None:
        self._current_bucket().names.add(name)

    def _add_attr_reference(self, name: str) -> None:
        self._current_bucket().attrs.add(name)

    def _resolve_method_reference(self, node: ast.Attribute) -> str | None:
        if not isinstance(node.value, ast.Name):
            return None
        target_name = node.value.id
        if target_name in self._class_methods and node.attr in self._class_methods[target_name]:
            return f"{target_name}.{node.attr}"
        if self._class_stack and target_name in {"self", "cls"}:
            current_class = self._class_stack[-1]
            if node.attr in self._class_methods.get(current_class, set()):
                return f"{current_class}.{node.attr}"
        return None

    def _visit_top_level_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self._scope_stack:
            self.generic_visit(node)
            return
        self._enter_definition(node.name)
        self.generic_visit(node)
        self._exit_definition()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_top_level_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_top_level_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        if self._scope_stack:
            self.generic_visit(node)
            return
        self._enter_definition(node.name)
        self._class_stack.append(node.name)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for type_param in getattr(node, "type_params", []):
            self.visit(type_param)
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_method(stmt, node.name)
            else:
                self.visit(stmt)
        self._class_stack.pop()
        self._exit_definition()

    def _visit_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef, class_name: str) -> None:
        method_key = f"{class_name}.{node.name}"
        self._enter_definition(method_key)
        self.generic_visit(node)
        self._exit_definition()

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        self._add_name_reference(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        self._add_attr_reference(node.attr)
        qualified = self._resolve_method_reference(node)
        if qualified is not None:
            self._add_name_reference(qualified)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        for alias in node.names:
            self._add_name_reference(alias.asname or alias.name)


def _collect_production_scan(src: Path) -> _ProductionScan:
    """Return definitions and production references split by module vs def scope."""
    defs: dict[str, list[str]] = {}
    def_refs: dict[str, _ReferenceBucket] = {}
    module_refs = _ReferenceBucket(names=set(), attrs=set())
    class_methods: dict[str, set[str]] = {}
    class_implicit_methods: dict[str, set[str]] = {}
    trees: list[tuple[Path, ast.AST]] = []
    implicit_decorators = {
        "model_validator",
        "field_validator",
        "validator",
        "root_validator",
        "computed_field",
        "field_serializer",
        "model_serializer",
    }

    def decorator_name(decorator: ast.AST) -> str | None:
        if isinstance(decorator, ast.Name):
            return decorator.id
        if isinstance(decorator, ast.Attribute):
            return decorator.attr
        if isinstance(decorator, ast.Call):
            return decorator_name(decorator.func)
        return None

    def has_implicit_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        return any(decorator_name(d) in implicit_decorators for d in node.decorator_list)

    for py_file in sorted(src.rglob("*.py")):
        if _is_test_file(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        trees.append((py_file, tree))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defs.setdefault(node.name, []).append(f"{py_file.relative_to(src)}:{node.lineno}")
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        class_methods.setdefault(node.name, set()).add(child.name)
                        method_key = f"{node.name}.{child.name}"
                        defs.setdefault(method_key, []).append(
                            f"{py_file.relative_to(src)}:{child.lineno}",
                        )
                        if has_implicit_decorator(child):
                            class_implicit_methods.setdefault(node.name, set()).add(child.name)
    method_aliases: dict[str, set[str]] = {}
    for class_name, methods in class_methods.items():
        for method_name in methods:
            method_aliases.setdefault(method_name, set()).add(f"{class_name}.{method_name}")

    for _, tree in trees:
        collector = _ReferenceCollector(class_methods)
        collector.visit(tree)
        module_refs.merge(collector.module_refs)
        for def_name, refs in collector.def_refs.items():
            def_refs.setdefault(def_name, _ReferenceBucket(names=set(), attrs=set())).merge(refs)

    return _ProductionScan(
        defs=defs,
        def_refs=def_refs,
        module_refs=module_refs,
        method_aliases=method_aliases,
        class_methods=class_methods,
        class_implicit_methods=class_implicit_methods,
    )


def _collect_references(src: Path, *, test_files: bool) -> _ReferenceBucket:
    """Return all names referenced in production files or test files.

    When test_files=True, collect from test files only.
    When test_files=False, collect from production files only.
    """
    refs = _ReferenceBucket(names=set(), attrs=set())
    for py_file in src.rglob("*.py"):
        is_test = _is_test_file(py_file)
        if test_files != is_test:
            continue
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                refs.names.add(node.id)
            elif isinstance(node, ast.Attribute):
                refs.attrs.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    refs.names.add(alias.name if alias.asname is None else alias.asname)
    return refs


def _resolve_live_definitions(
    defs: dict[str, list[str]],
    def_refs: dict[str, _ReferenceBucket],
    module_refs: _ReferenceBucket,
    method_aliases: dict[str, set[str]],
    class_methods: dict[str, set[str]],
    class_implicit_methods: dict[str, set[str]],
) -> set[str]:
    live: set[str] = set()
    stack: list[str] = []

    def add_class_method(class_name: str, method_name: str) -> None:
        method_key = f"{class_name}.{method_name}"
        if method_key in defs and method_key not in live:
            live.add(method_key)
            stack.append(method_key)

    def add_live(name: str) -> None:
        if name in defs and name not in live:
            live.add(name)
            stack.append(name)
            if name in class_methods:
                for method_name in class_methods[name]:
                    if method_name.startswith("__") and method_name.endswith("__"):
                        add_class_method(name, method_name)
                for method_name in class_implicit_methods.get(name, set()):
                    add_class_method(name, method_name)

    def add_attr_live(name: str) -> None:
        add_live(name)
        for method_key in method_aliases.get(name, set()):
            if method_key not in live:
                live.add(method_key)
                stack.append(method_key)

    for name in module_refs.names:
        add_live(name)
    for name in module_refs.attrs:
        add_attr_live(name)
    while stack:
        name = stack.pop()
        refs = def_refs.get(name)
        if refs is None:
            continue
        for ref in refs.names:
            add_live(ref)
        for ref in refs.attrs:
            add_attr_live(ref)
    return live


def find_dead_code(src: Path) -> DeadCodeReport:
    scan = _collect_production_scan(src)
    test_refs = _collect_references(src, test_files=True)
    live = _resolve_live_definitions(
        scan.defs,
        scan.def_refs,
        scan.module_refs,
        scan.method_aliases,
        scan.class_methods,
        scan.class_implicit_methods,
    )
    test_referenced_defs: set[str] = set()
    for name in test_refs.names:
        if name in scan.defs:
            test_referenced_defs.add(name)
    for name in test_refs.attrs:
        if name in scan.defs:
            test_referenced_defs.add(name)
        test_referenced_defs.update(scan.method_aliases.get(name, set()))

    test_only: list[tuple[str, str]] = []
    unreferenced: list[tuple[str, str]] = []
    for name, locations in sorted(scan.defs.items()):
        if name in live:
            continue
        target = test_only if name in test_referenced_defs else unreferenced
        for loc in locations:
            target.append((loc, name))
    return DeadCodeReport(test_only=test_only, unreferenced=unreferenced)


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "src")
    report = find_dead_code(src)

    if not report.all_dead():
        return 0

    if report.test_only:
        print("Production code only referenced from tests (dead code):")
        for loc, name in report.test_only:
            print(f"  {loc}: {name}")
    if report.unreferenced:
        print("Production code with no references (dead code):")
        for loc, name in report.unreferenced:
            print(f"  {loc}: {name}")
    print("Note: Detected dead code should be removed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
