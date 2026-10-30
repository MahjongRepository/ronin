from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scripts.fixture_files import FixtureDir
from scripts.replay_fixtures.scenarios import FIXTURES
from shared.logging import setup_logging

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = FixtureDir(REPO_ROOT / "frontend" / "game_v2" / "src" / "fixtures" / "replays", suffix=".txt")
DESCRIPTION = """
Generate the replay files the v2 game client's tests read, by playing the scenarios of scripts.replay_fixtures through
the real engine: games dealt from a staged wall and played seat by seat, a game dealt from its seed and played by a
fixed policy, a recorded backend replay run again, and cuts of those. Each replay must reproduce its game through the
replay runner before it is written. With --check nothing is written: the run fails, naming each fixture, when a
committed fixture differs from what the engine records now, is missing, or has no scenario.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--check", action="store_true", help="fail on drift instead of writing the fixtures")
    args = parser.parse_args()

    setup_logging(level=logging.WARNING)
    generated = {name: build().text for name, build in FIXTURES.items()}
    if not args.check:
        FIXTURES_DIR.write(generated)
        print(f"wrote {len(generated)} replay fixture(s) to {FIXTURES_DIR.path.relative_to(REPO_ROOT)}")
        return 0

    problems = FIXTURES_DIR.find_drift(generated)
    for problem in problems:
        print(problem)

    if problems:
        print("replay fixtures drifted from the engine: run `make generate-replay-fixtures` and update the client")
        return 1

    print(f"{len(generated)} replay fixture(s) up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
