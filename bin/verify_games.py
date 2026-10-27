"""
Check that each played game ended as completed and that its saved replay reproduces it.

For every game id: its played_games row must record the completed end reason, its replay file must exist, and running
the replay through the engine must emit the round ends and game end the file recorded. Exits 1 when any game fails or
no game id is given. Reads the replay directory and database path from the game server's settings (the environment
`bin/local-settings.sh` exports).

Usage: uv run --project backend python bin/verify_games.py <game_id>...
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sqlite3
import sys
import traceback
from pathlib import Path
from typing import Any

from game.logic.events import GameEndedEvent, RoundEndEvent
from game.messaging.event_payload import game_event_payload
from game.replay import load_replay_from_file, run_replay
from game.server.settings import GameServerSettings
from game.wire.enums import WireEventType
from shared.dal.models import GameEndReason
from shared.logging import setup_logging
from shared.storage import replay_file_path

OUTCOME_EVENT_TYPES = frozenset({WireEventType.ROUND_END, WireEventType.GAME_END})


def read_end_reason(database_path: Path, game_id: str) -> str | None:
    with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as conn:
        row = conn.execute("SELECT end_reason FROM played_games WHERE id = ?", (game_id,)).fetchone()

    return row[0] if row else None


def read_recorded_outcomes(replay_path: Path) -> list[dict[str, Any]]:
    with gzip.open(replay_path, "rt", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f.read().splitlines()[1:]]

    return [line for line in lines if line["t"] in OUTCOME_EVENT_TYPES]


def replay_outcomes(replay_path: Path) -> list[dict[str, Any]]:
    trace = run_replay(load_replay_from_file(replay_path))
    return [
        json.loads(json.dumps(game_event_payload(event)))
        for event in trace.events
        if isinstance(event, RoundEndEvent | GameEndedEvent)
    ]


def find_outcome_mismatch(recorded: list[dict[str, Any]], replayed: list[dict[str, Any]]) -> str | None:
    for index, (recorded_line, replayed_line) in enumerate(zip(recorded, replayed, strict=False)):
        if recorded_line != replayed_line:
            return f"outcome {index} differs:\n    recorded: {recorded_line}\n    replayed: {replayed_line}"

    if len(recorded) != len(replayed):
        return f"recorded {len(recorded)} outcomes, replay emitted {len(replayed)}"

    return None


def verify_game(settings: GameServerSettings, game_id: str) -> str | None:
    """
    Return why the game fails verification, or None when it passes.
    """
    end_reason = read_end_reason(Path(settings.database_path), game_id)
    if end_reason != GameEndReason.COMPLETED:
        return f"end reason is {end_reason!r}, expected {GameEndReason.COMPLETED.value!r}"

    replay_path = replay_file_path(Path(settings.replay_dir), game_id)
    if not replay_path.is_file():
        return f"no replay at {replay_path}"

    recorded = read_recorded_outcomes(replay_path)
    if not any(line["t"] == WireEventType.GAME_END for line in recorded):
        return "replay records no game end"

    try:
        replayed = replay_outcomes(replay_path)
    except Exception:  # noqa: BLE001 (any replay failure is this game's verdict)
        return f"replay failed:\n{traceback.format_exc()}"

    return find_outcome_mismatch(recorded, replayed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game_ids", nargs="*")
    args = parser.parse_args()
    if not args.game_ids:
        print("no game ids to verify")
        return 1

    setup_logging(level=logging.WARNING)
    settings = GameServerSettings()

    failures = 0
    for game_id in args.game_ids:
        problem = verify_game(settings, game_id)
        if problem is None:
            print(f"ok      {game_id}")
            continue

        failures += 1
        print(f"FAILED  {game_id}: {problem}")

    print(f"{len(args.game_ids) - failures}/{len(args.game_ids)} game(s) verified")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
