from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any

from game.logic.rng import RNG_VERSION, SEED_BYTES
from scripts.measure_wall.measurement import Measurement
from scripts.measure_wall.report import render_baseline, render_text, to_json
from scripts.measure_wall.sampling import CONTROL_METHOD, control_rounds, engine_seeds, sample_engine_game

DESCRIPTION = """
Measure the wall generator: sample games from the engine's own seed, dealer and wall functions and compare what comes
out with exact references (tile by position, dice, first dealer, seats, hand composition) and, for starting-hand
shanten, with an independent stdlib shuffle. Structural failures (a wall that does not own every tile once, a game
that does not regenerate from its seed) exit 1; statistical warnings are printed and never fail the run, since under
a correct generator each family warns with at most a 0.1% chance. Edit a constant in game/logic/rng.py, rerun, and
compare with --baseline against the JSON of the previous run; give the rerun another --experiment-seed to get an
independent comparison with z scores rather than paired differences.
"""
DEFAULT_GAMES = 5000
DEFAULT_ROUNDS = 4


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    Parse the run's size, its experiment seed and where to write or read JSON.
    """
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=DEFAULT_GAMES, help="games to sample")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help="rounds (walls) per game")
    parser.add_argument("--experiment-seed", type=int, default=0, help="fixes the engine seeds and the control shuffle")
    parser.add_argument("--json", type=Path, help="write the report with raw counts here")
    parser.add_argument("--baseline", type=Path, help="a JSON report of an earlier run to compare with")
    args = parser.parse_args(argv)
    if args.games < 1 or args.rounds < 1:
        parser.error("--games and --rounds must be at least 1")

    return args


def run(games: int, rounds: int, experiment_seed: int) -> tuple[Measurement, dict[str, Any]]:
    """
    Sample the engine and the control, then return the measurement and the run's metadata.
    """
    started = time.perf_counter()
    measurement = Measurement()
    first_game = None
    for seed in engine_seeds(experiment_seed, games):
        game = sample_engine_game(seed, rounds)
        first_game = first_game or game
        measurement.observe_engine(game)

    if first_game is not None:
        measurement.verify_regeneration(first_game)

    for batch in batched(control_rounds(experiment_seed, games * rounds), rounds, strict=True):
        measurement.observe_control(list(batch))

    elapsed = time.perf_counter() - started
    metadata = {
        "rng_version": RNG_VERSION,
        "seed_bytes": SEED_BYTES,
        "games": games,
        "rounds": rounds,
        "experiment_seed": experiment_seed,
        "control_method": CONTROL_METHOD,
        "python": platform.python_version(),
        "started_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "elapsed_seconds": elapsed,
        "walls_per_second": measurement.walls / elapsed if elapsed else 0.0,
    }
    return measurement, metadata


def main(argv: list[str]) -> int:
    """
    Run the measurement, print the report, write the JSON when asked, and exit 1 only on a structural error.
    """
    args = parse_args(argv)
    measurement, metadata = run(args.games, args.rounds, args.experiment_seed)
    report = measurement.report(metadata, CONTROL_METHOD)
    print(render_text(report))
    if args.baseline:
        print()
        print(render_baseline(report, args.baseline))

    if args.json:
        args.json.write_text(json.dumps(to_json(report, measurement.family_json())), encoding="utf-8")
        print(f"\nJSON written to {args.json}")

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
