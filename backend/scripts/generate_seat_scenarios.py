from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scripts.fixture_files import FixtureDir
from scripts.seat_scenarios.scenarios import SCENARIOS
from shared.logging import setup_logging

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = FixtureDir(
    REPO_ROOT / "frontend" / "game_v2" / "tests" / "fixtures" / "seat-scenarios",
    suffix=".json",
)
DESCRIPTION = """
Generate the seat transcripts the v2 game client's scenario tests read, by playing the scenarios of
scripts.seat_scenarios through the real session manager, message router and engine on virtual time: what each named
seat's client received, the game actions it sent, and the sockets it opened and saw close. With --check nothing is
written: the run fails, naming each transcript, when a committed one differs from what the server sends now, is missing,
or has no scenario.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--check", action="store_true", help="fail on drift instead of writing the transcripts")
    args = parser.parse_args()

    setup_logging(level=logging.WARNING)
    generated = {transcript.file_name: transcript.text for build in SCENARIOS.values() for transcript in build()}
    if not args.check:
        SCENARIOS_DIR.write(generated)
        print(f"wrote {len(generated)} seat transcript(s) to {SCENARIOS_DIR.path.relative_to(REPO_ROOT)}")
        return 0

    problems = SCENARIOS_DIR.find_drift(generated)
    for problem in problems:
        print(problem)

    if problems:
        print("seat transcripts drifted from the server: run `make generate-seat-scenarios` and update the client")
        return 1

    print(f"{len(generated)} seat transcript(s) up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
