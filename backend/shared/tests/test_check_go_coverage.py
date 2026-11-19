from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

ENGINE_BLOCK = "github.com/MahjongRepository/ronin/backend/game_v2/engine/engine.go:45.41,48.2"
RULES_BLOCK = "github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules/wall.go:7.26,9.2"
MARKER_BLOCK = "github.com/MahjongRepository/ronin/backend/game_v2/engine/play/event.go:20.27,20.27"


def _load_check_go_coverage_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "bin" / "check_go_coverage.py"
    spec = importlib.util.spec_from_file_location("check_go_coverage", module_path)
    assert spec is not None

    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_profile(tmp_path: Path, lines: list[str]) -> Path:
    profile = tmp_path / "coverage.out"
    profile.write_text("".join(f"{line}\n" for line in ["mode: atomic", *lines]))
    return profile


def test_main__when_block_is_missed_by_one_test_binary_and_hit_by_another__should_pass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    check_go_coverage = _load_check_go_coverage_module()
    profile = _write_profile(
        tmp_path,
        [f"{ENGINE_BLOCK} 2 0", f"{RULES_BLOCK} 1 0", f"{ENGINE_BLOCK} 2 3", f"{RULES_BLOCK} 1 1"],
    )

    status = check_go_coverage.main([str(profile)])

    assert status == 0
    assert capsys.readouterr().err == ""


def test_main__when_block_is_missed_by_every_test_binary__should_fail_and_print_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    check_go_coverage = _load_check_go_coverage_module()
    profile = _write_profile(tmp_path, [f"{ENGINE_BLOCK} 2 0", f"{RULES_BLOCK} 1 4", f"{ENGINE_BLOCK} 2 0"])

    status = check_go_coverage.main([str(profile)])

    assert status == 1
    assert capsys.readouterr().err == f"uncovered: {ENGINE_BLOCK}\n"


def test_main__when_an_unrun_block_holds_no_statement__should_pass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    check_go_coverage = _load_check_go_coverage_module()
    profile = _write_profile(tmp_path, [f"{MARKER_BLOCK} 0 0", f"{ENGINE_BLOCK} 2 1"])

    status = check_go_coverage.main([str(profile)])

    assert status == 0
    assert capsys.readouterr().err == ""
