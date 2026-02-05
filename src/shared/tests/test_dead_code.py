from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path


def _load_dead_code_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "bin" / "check-dead-code.py"
    spec = importlib.util.spec_from_file_location("check_dead_code", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_dedent(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip("\n"))


def test_reports_test_only_chain(tmp_path: Path) -> None:
    dead_code = _load_dead_code_module()
    src_dir = tmp_path / "src"
    prod_dir = src_dir / "game" / "logic"
    test_dir = src_dir / "game" / "tests" / "unit"
    prod_dir.mkdir(parents=True)
    test_dir.mkdir(parents=True)

    _write_dedent(
        prod_dir / "tiles.py",
        """
        def tile_to_string(tile_id):
            return tile_34_to_string(tile_id)

        def tile_34_to_string(tile_34):
            return "1m"

        def unused():
            return 1
        """,
    )
    _write_dedent(
        test_dir / "test_tiles.py",
        """
        from game.logic.tiles import tile_34_to_string, tile_to_string

        def test_tiles():
            assert tile_to_string(0) == tile_34_to_string(0)
        """,
    )

    report = dead_code.find_dead_code(src_dir)
    dead_names = {name for _, name in report.test_only}
    assert dead_names == {"tile_to_string", "tile_34_to_string"}
    unreferenced_names = {name for _, name in report.unreferenced}
    assert unreferenced_names == {"unused"}


def test_does_not_report_production_chain(tmp_path: Path) -> None:
    dead_code = _load_dead_code_module()
    src_dir = tmp_path / "src"
    prod_dir = src_dir / "game" / "logic"
    test_dir = src_dir / "game" / "tests" / "unit"
    prod_dir.mkdir(parents=True)
    test_dir.mkdir(parents=True)

    _write_dedent(
        prod_dir / "core.py",
        """
        def helper():
            return 1

        def handler():
            return helper()
        """,
    )
    _write_dedent(
        prod_dir / "app.py",
        """
        from game.logic.core import handler

        HANDLER = handler
        """,
    )
    _write_dedent(
        test_dir / "test_core.py",
        """
        from game.logic.core import handler, helper

        def test_core():
            assert handler() == helper()
        """,
    )

    report = dead_code.find_dead_code(src_dir)
    assert report.all_dead() == []


def test_reports_unreferenced_definitions(tmp_path: Path) -> None:
    dead_code = _load_dead_code_module()
    src_dir = tmp_path / "src"
    prod_dir = src_dir / "lobby" / "logic"
    prod_dir.mkdir(parents=True)

    _write_dedent(
        prod_dir / "unused.py",
        """
        def _helper():
            return 1

        def unused():
            return _helper()
        """,
    )

    report = dead_code.find_dead_code(src_dir)
    dead_names = {name for _, name in report.unreferenced}
    assert dead_names == {"_helper", "unused"}
    assert report.test_only == []


def test_reports_unused_methods(tmp_path: Path) -> None:
    dead_code = _load_dead_code_module()
    src_dir = tmp_path / "src"
    prod_dir = src_dir / "game" / "logic"
    prod_dir.mkdir(parents=True)

    _write_dedent(
        prod_dir / "player.py",
        """
        class Player:
            def used(self):
                return self._helper()

            def _helper(self):
                return 1

            def not_used_method(self):
                return 2
        """,
    )
    _write_dedent(
        prod_dir / "app.py",
        """
        from game.logic.player import Player

        PLAYER = Player()
        PLAYER.used()
        """,
    )

    report = dead_code.find_dead_code(src_dir)
    dead_names = {name for _, name in report.unreferenced}
    assert "Player.not_used_method" in dead_names
    assert "Player._helper" not in dead_names
    assert "Player.used" not in dead_names


def test_keeps_decorated_methods_when_class_is_live(tmp_path: Path) -> None:
    dead_code = _load_dead_code_module()
    src_dir = tmp_path / "src"
    prod_dir = src_dir / "game" / "logic"
    prod_dir.mkdir(parents=True)

    _write_dedent(
        prod_dir / "events.py",
        """
        def model_validator(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        class Service:
            @model_validator(mode="after")
            def _ensure(self):
                return self

        SERVICE = Service()
        """,
    )

    report = dead_code.find_dead_code(src_dir)
    assert report.all_dead() == []
