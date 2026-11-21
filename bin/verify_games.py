"""
Check that each played game ended as completed and that its saved replay reproduces it.

For every game id: its played_games row must record the completed end reason, and the Go server's replay check (its
cmd/verify binary) must run its replay through the Go engine to the outcomes the file recorded. Exits 1 when any game
fails or no game id is given. Reads the replay directory and database path from GAME_REPLAY_DIR and
AUTH_DATABASE_PATH (the environment `bin/local-settings.sh` exports).

Usage: uv run --project backend python bin/verify_games.py <verify binary> <game_id>...
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from lobby.dal.models import GameEndReason

VERIFY_FAILED = 1
OK_PREFIX = "ok      "
FAILED_PREFIX = "FAILED  "


@dataclass(frozen=True)
class Paths:
    replay_dir: Path
    database_path: Path


def read_paths() -> Paths:
    missing = [name for name in ("GAME_REPLAY_DIR", "AUTH_DATABASE_PATH") if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing environment: {', '.join(missing)}")

    return Paths(replay_dir=Path(os.environ["GAME_REPLAY_DIR"]), database_path=Path(os.environ["AUTH_DATABASE_PATH"]))


def read_end_reason(database_path: Path, game_id: str) -> str | None:
    with closing(sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)) as conn:
        row = conn.execute("SELECT end_reason FROM played_games WHERE id = ?", (game_id,)).fetchone()

    return row[0] if row else None


def verify_replay(verify: Path, replay_dir: Path, game_id: str) -> str | None:
    result = subprocess.run(  # noqa: S603 (the Go replay check this run built, given its own game ids)
        [str(verify), "-replay-dir", str(replay_dir), game_id],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = result.stdout.splitlines()
    if result.returncode == 0 and lines and lines[0] == f"{OK_PREFIX}{game_id}":
        return None

    failed_prefix = f"{FAILED_PREFIX}{game_id}: "
    if result.returncode == VERIFY_FAILED and lines and lines[0].startswith(failed_prefix):
        return "\n".join([lines[0].removeprefix(failed_prefix), *lines[1:-1]])

    return f"the Go replay check exited {result.returncode}:\n{result.stdout}{result.stderr}"


def verify_game(verify: Path, paths: Paths, game_id: str) -> str | None:
    """
    Return why the game fails verification, or None when it passes.
    """
    end_reason = read_end_reason(paths.database_path, game_id)
    if end_reason != GameEndReason.COMPLETED:
        return f"end reason is {end_reason!r}, expected {GameEndReason.COMPLETED.value!r}"

    return verify_replay(verify=verify, replay_dir=paths.replay_dir, game_id=game_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("verify", type=Path, help="the Go server's replay check binary to replay each game with")
    parser.add_argument("game_ids", nargs="*")
    args = parser.parse_args()
    if not args.game_ids:
        print("no game ids to verify")
        return 1

    paths = read_paths()

    failures = 0
    for game_id in args.game_ids:
        problem = verify_game(verify=args.verify, paths=paths, game_id=game_id)
        if problem is None:
            print(f"{OK_PREFIX}{game_id}")
            continue

        failures += 1
        print(f"{FAILED_PREFIX}{game_id}: {problem}")

    print(f"{len(args.game_ids) - failures}/{len(args.game_ids)} game(s) verified")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
