from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SITE = "/venv/lib/python3.14/site-packages"
APP = "/repo/backend"


def _load_sampled_profile_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "bin" / "sampled_profile.py"
    spec = importlib.util.spec_from_file_location("sampled_profile", module_path)
    assert spec is not None

    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_samples(tmp_path: Path, stacks: dict[tuple[str, ...], int]) -> Path:
    sample_file = tmp_path / "samples.txt"
    sample_file.write_text("".join(f"{';'.join(frames)} {count}\n" for frames, count in stacks.items()))
    return sample_file


def test_summarize_samples__when_library_code_is_deepest__should_charge_the_layer_that_called_it(tmp_path: Path):
    sampled_profile = _load_sampled_profile_module()
    endpoint = f"ws_endpoint ({APP}/game/server/app.py:238)"
    sample_file = _write_samples(
        tmp_path,
        {
            (
                endpoint,
                f"handle_game_action ({APP}/game/session/manager.py:469)",
                f"handle_action ({APP}/game/logic/mahjong_service.py:212)",
                f"model_copy ({SITE}/pydantic/main.py:410)",
            ): 5,
            (
                f"_write_queue ({APP}/shared/websocket.py:119)",
                f"send ({SITE}/uvicorn/protocols/websockets/websockets_sansio_impl.py:432)",
            ): 3,
            (endpoint, f"bind ({SITE}/structlog/_config.py:350)"): 2,
        },
    )

    summary = sampled_profile.summarize_samples(sample_file, root=None)

    assert summary.total == 10
    assert summary.layer_samples == {"engine": 5, "uvicorn and websockets": 3, "server and router": 2}


def test_summarize_samples__when_stack_imports_or_misses_root__should_leave_it_out(tmp_path: Path):
    sampled_profile = _load_sampled_profile_module()
    loop = f"run_replay_loop ({APP}/bin/profile_replay.py:75)"
    sample_file = _write_samples(
        tmp_path,
        {
            (loop, f"run_replay ({APP}/game/replay/runner.py:77)"): 7,
            (loop, f"__del__ ({SITE}/pydantic/main.py:300)"): 2,
            (loop, "_find_and_load (<frozen importlib._bootstrap>:1360)"): 1,
            (f"<module> ({APP}/bin/profile_replay.py:1)",): 4,
        },
    )

    summary = sampled_profile.summarize_samples(sample_file, root="run_replay_loop")

    assert summary.total == 9
    assert summary.excluded == 5


@pytest.mark.parametrize(
    ("output", "problem"),
    [
        ("py-spy> Wrote raw flamegraph data to 'x'. Samples: 2180 Errors: 0", None),
        ("py-spy> Sampling process 100 times a second.", "py-spy printed no sample summary"),
        ("py-spy> Wrote raw flamegraph data to 'x'. Samples: 0 Errors: 0", "py-spy recorded no samples"),
        ("py-spy> Wrote raw flamegraph data to 'x'. Samples: 37 Errors: 282", "py-spy lost 282 samples"),
        (
            "py-spy> 1.04s behind in sampling, results may be inaccurate.\nSamples: 900 Errors: 0",
            "py-spy fell behind in sampling",
        ),
    ],
)
def test_py_spy_output_problem__when_output_varies__should_accept_only_complete_profiles(
    output: str, problem: str | None
):
    sampled_profile = _load_sampled_profile_module()

    assert sampled_profile.py_spy_output_problem(output) == problem
