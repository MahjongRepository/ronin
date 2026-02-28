"""Replay API handler for serving gzip-compressed replay files."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.requests import Request

# Game ID must be alphanumeric with hyphens/underscores, max 50 chars.
_GAME_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_GAME_ID_MAX_LEN = 50

# Reject replay files larger than 1 MB (defense against corrupted files).
_MAX_FILE_SIZE = 1_048_576

_NOT_FOUND = Response("Not found", status_code=404, media_type="text/plain")


def _load_replay(replay_dir_str: str, game_id: str) -> bytes | None:
    """Resolve paths and read a gzip-compressed replay file.

    Returns the raw gzip bytes, or None if the file is missing, too large,
    or the game_id resolves outside the replay directory.
    """
    replay_dir = Path(replay_dir_str).resolve()
    target = (replay_dir / f"{game_id}.txt.gz").resolve()

    if not target.is_relative_to(replay_dir):
        return None

    try:
        with target.open("rb") as f:
            data = f.read(_MAX_FILE_SIZE + 1)
    except OSError:
        return None

    if len(data) > _MAX_FILE_SIZE:
        return None

    return data


async def replay_content(request: Request) -> Response:
    """GET /api/replays/{game_id} — serve a gzip-compressed replay file."""
    game_id = request.path_params["game_id"]

    if not game_id or len(game_id) > _GAME_ID_MAX_LEN or not _GAME_ID_RE.match(game_id):
        return _NOT_FOUND

    replay_dir_str: str = request.app.state.settings.replay_dir
    gzip_bytes = await asyncio.to_thread(_load_replay, replay_dir_str, game_id)
    if gzip_bytes is None:
        return _NOT_FOUND

    return Response(
        content=gzip_bytes,
        media_type="application/x-ndjson",
        headers={
            "Content-Encoding": "gzip",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
