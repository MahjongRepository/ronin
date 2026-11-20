"""
Check that each played game ended as completed and that its saved replay reproduces it.

For every game id: its played_games row must record the completed end reason, its replay file must exist, and running
the replay through the engine must emit the round ends and game end the file recorded. With --go-verify, the Go
server's replay check (its cmd/verify binary) runs each replay through the Go engine instead. Exits 1 when any game
fails or no game id is given. Reads the replay directory and database path from the game server's settings (the
environment `bin/local-settings.sh` exports).

Usage: uv run --project backend python bin/verify_games.py [--go-verify <verify binary>] <game_id>...
"""

from __future__ import annotations

import argparse
import gzip
import logging
import sqlite3
import subprocess
import sys
import traceback
from contextlib import closing
from pathlib import Path
from typing import Any

from game.engine import GameEndedEvent, RoundEndEvent
from game.messaging.event_payload import game_event_payload
from game.replay import load_replay_from_file, run_replay
from game.server.settings import GameServerSettings
from game.wire.enums import WireEventType
from game.wire.keys import WireKey
from game.wire.replay_format import MAX_REPLAY_BYTES, decode_replay_records
from shared.dal.models import GameEndReason
from shared.logging import setup_logging
from shared.storage import replay_file_path

OUTCOME_EVENT_TYPES = frozenset({WireEventType.ROUND_END, WireEventType.GAME_END})
GO_VERIFY_FAILED = 1
GO_VERIFY_OK_PREFIX = "ok      "
GO_VERIFY_FAILED_PREFIX = "FAILED  "


def read_end_reason(database_path: Path, game_id: str) -> str | None:
    with closing(sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)) as conn:
        row = conn.execute("SELECT end_reason FROM played_games WHERE id = ?", (game_id,)).fetchone()

    return row[0] if row else None


def read_recorded_outcomes(replay_path: Path) -> list[dict[int, Any]]:
    with gzip.open(replay_path, "rb") as f:
        lines = decode_replay_records(f.read(MAX_REPLAY_BYTES + 1))[1:]

    return [line for line in lines if line[WireKey.EVENT_TYPE] in OUTCOME_EVENT_TYPES]


def replay_outcomes(replay_path: Path) -> list[dict[int, Any]]:
    trace = run_replay(load_replay_from_file(replay_path))
    return [game_event_payload(event) for event in trace.events if isinstance(event, RoundEndEvent | GameEndedEvent)]


def find_outcome_mismatch(recorded: list[dict[int, Any]], replayed: list[dict[int, Any]]) -> str | None:
    for index, (recorded_line, replayed_line) in enumerate(zip(recorded, replayed, strict=False)):
        if recorded_line != replayed_line:
            return f"outcome {index} differs:\n    recorded: {recorded_line}\n    replayed: {replayed_line}"

    if len(recorded) != len(replayed):
        return f"recorded {len(recorded)} outcomes, replay emitted {len(replayed)}"

    return None


def verify_replay(settings: GameServerSettings, game_id: str) -> str | None:
    replay_path = replay_file_path(Path(settings.replay_dir), game_id)
    if not replay_path.is_file():
        return f"no replay at {replay_path}"

    recorded = read_recorded_outcomes(replay_path)
    if not any(line[WireKey.EVENT_TYPE] == WireEventType.GAME_END for line in recorded):
        return "replay records no game end"

    try:
        replayed = replay_outcomes(replay_path)
    except Exception:  # noqa: BLE001 (any replay failure is this game's verdict)
        return f"replay failed:\n{traceback.format_exc()}"

    return find_outcome_mismatch(recorded, replayed)


def verify_replay_in_go(go_verify: Path, settings: GameServerSettings, game_id: str) -> str | None:
    result = subprocess.run(  # noqa: S603 (the Go replay check this run built, given its own game ids)
        [str(go_verify), "-replay-dir", str(settings.replay_dir), game_id],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = result.stdout.splitlines()
    if result.returncode == 0 and lines and lines[0] == f"{GO_VERIFY_OK_PREFIX}{game_id}":
        return None

    failed_prefix = f"{GO_VERIFY_FAILED_PREFIX}{game_id}: "
    if result.returncode == GO_VERIFY_FAILED and lines and lines[0].startswith(failed_prefix):
        return "\n".join([lines[0].removeprefix(failed_prefix), *lines[1:-1]])

    return f"the Go replay check exited {result.returncode}:\n{result.stdout}{result.stderr}"


def verify_game(settings: GameServerSettings, game_id: str, go_verify: Path | None) -> str | None:
    """
    Return why the game fails verification, or None when it passes.
    """
    end_reason = read_end_reason(Path(settings.database_path), game_id)
    if end_reason != GameEndReason.COMPLETED:
        return f"end reason is {end_reason!r}, expected {GameEndReason.COMPLETED.value!r}"

    if go_verify is not None:
        return verify_replay_in_go(go_verify, settings, game_id)

    return verify_replay(settings, game_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--go-verify", type=Path, help="the Go server's replay check binary to replay each game with")
    parser.add_argument("game_ids", nargs="*")
    args = parser.parse_args()
    if not args.game_ids:
        print("no game ids to verify")
        return 1

    setup_logging(level=logging.WARNING)
    settings = GameServerSettings()

    failures = 0
    for game_id in args.game_ids:
        problem = verify_game(settings, game_id, args.go_verify)
        if problem is None:
            print(f"ok      {game_id}")
            continue

        failures += 1
        print(f"FAILED  {game_id}: {problem}")

    print(f"{len(args.game_ids) - failures}/{len(args.game_ids)} game(s) verified")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
