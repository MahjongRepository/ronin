from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scripts.replay_fixtures.scenarios import FIXTURES
from shared.logging import setup_logging

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "frontend" / "game" / "src" / "js" / "__tests__" / "fixtures" / "replays"
DESCRIPTION = """
Generate the replay files the game client's tests read, by playing the scenarios of scripts.replay_fixtures through
the real engine: games dealt from a staged wall and played seat by seat, a game dealt from its seed and played by a
fixed policy, a recorded backend replay run again, and cuts of those. Each replay must reproduce its game through the
replay runner before it is written. With --check nothing is written: the run fails, naming each fixture, when a
committed fixture differs from what the engine records now, is missing, or has no scenario.
"""


def find_drift(generated: dict[str, str]) -> list[str]:
    """
    Name each committed fixture that differs from its generated text, is missing, or has no scenario.
    """
    committed = {path.name for path in FIXTURE_DIR.glob("*.txt")}
    problems = [f"orphaned: {name} (no scenario produces it)" for name in sorted(committed - generated.keys())]
    for name, text in generated.items():
        if name not in committed:
            problems.append(f"missing: {name}")
            continue

        if (FIXTURE_DIR / name).read_text(encoding="utf-8") != text:
            problems.append(f"stale: {name}")

    return problems


def write_fixtures(generated: dict[str, str]) -> None:
    """
    Write every generated fixture and delete the committed ones no scenario produces.
    """
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(FIXTURE_DIR.glob("*.txt")):
        if path.name not in generated:
            path.unlink()
            print(f"removed {path.name}")

    for name, text in generated.items():
        (FIXTURE_DIR / name).write_text(text, encoding="utf-8")

    print(f"wrote {len(generated)} replay fixture(s) to {FIXTURE_DIR.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--check", action="store_true", help="fail on drift instead of writing the fixtures")
    args = parser.parse_args()

    setup_logging(level=logging.WARNING)
    generated = {name: build().text for name, build in FIXTURES.items()}
    if not args.check:
        write_fixtures(generated)
        return 0

    problems = find_drift(generated)
    for problem in problems:
        print(problem)

    if problems:
        print("replay fixtures drifted from the engine: run `make generate-replay-fixtures` and update the client")
        return 1

    print(f"{len(generated)} replay fixture(s) up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
