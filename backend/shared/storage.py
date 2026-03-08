"""Storage abstraction for replay persistence.

Replay files are gzip-compressed NDJSON containing full game event logs.
Replays are public and served to any user via the lobby replay API.
Files are written with owner-only permissions (0o600) inside owner-only
directories (0o700) as a filesystem hygiene measure.

Replay files are distributed across a two-level directory structure using
the first 4 characters of the game ID as shard prefixes:
``{replay_dir}/{id[0:2]}/{id[2:4]}/{game_id}.txt.gz``
"""

import contextlib
import gzip
import os
import tempfile
from pathlib import Path
from typing import Protocol

import structlog

logger = structlog.get_logger()

# Owner-only directory permissions for replay storage.
_REPLAY_DIR_MODE = 0o700

# Owner-only file permissions for replay data files.
_REPLAY_FILE_MODE = 0o600

# Game IDs shorter than this cannot produce a two-level shard prefix.
_MIN_GAME_ID_LEN = 4


def replay_file_path(replay_dir: Path, game_id: str) -> Path:
    """Build the sharded file path for a replay.

    Use the first 4 characters of game_id as a two-level directory
    prefix (2 chars each) to distribute files across subdirectories.
    Require game_id to be at least 4 characters long.
    """
    if len(game_id) < _MIN_GAME_ID_LEN:
        raise ValueError(f"game_id must be at least {_MIN_GAME_ID_LEN} characters, got {len(game_id)}")
    prefix_a = game_id[:2]
    prefix_b = game_id[2:4]
    return replay_dir / prefix_a / prefix_b / f"{game_id}.txt.gz"


class ReplayStorage(Protocol):
    """Protocol for persisting replay data."""

    def save_replay(self, game_id: str, content: str) -> None: ...


class LocalReplayStorage:
    """Write gzip-compressed replay files to the local filesystem.

    Files are created with owner-only read/write (0o600) inside owner-only
    directories (0o700) as a filesystem hygiene measure. Replay files are
    distributed across a two-level shard directory structure.
    """

    def __init__(self, replay_dir: str) -> None:
        self._replay_dir = Path(replay_dir).resolve()

    def save_replay(self, game_id: str, content: str) -> None:
        """Save gzip-compressed replay content under the configured directory.

        Create shard directories lazily on first write with owner-only
        permissions (0o700). Write replay files atomically via
        temp-file-then-rename with owner-only permissions (0o600). Reject
        path traversal attempts that would place the file outside the replay
        root.
        """
        target = replay_file_path(self._replay_dir, game_id).resolve()
        if not target.is_relative_to(self._replay_dir):
            raise ValueError(f"Path traversal rejected: '{game_id}' resolves outside replay directory")

        shard_dir = target.parent
        shard_dir.mkdir(mode=_REPLAY_DIR_MODE, parents=True, exist_ok=True)
        # Ensure owner-only permissions on all directory levels (mkdir
        # parents=True applies mode only to the leaf; umask may weaken it).
        for directory in (self._replay_dir, shard_dir.parent, shard_dir):
            directory.chmod(_REPLAY_DIR_MODE)

        compressed = gzip.compress(content.encode("utf-8"))

        fd, tmp_path = tempfile.mkstemp(dir=str(shard_dir), suffix=".tmp", prefix=".replay_")
        fd_owned = True
        try:
            with os.fdopen(fd, "wb") as f:
                fd_owned = False  # os.fdopen took ownership; it will close fd
                f.write(compressed)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, _REPLAY_FILE_MODE)  # noqa: PTH101
            Path(tmp_path).replace(target)
        except BaseException:
            if fd_owned:
                with contextlib.suppress(OSError):
                    os.close(fd)
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()
            raise
        logger.info("saved replay", game_id=game_id, path=str(target))
