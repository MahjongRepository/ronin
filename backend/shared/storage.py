"""Storage abstraction for replay persistence.

Replay files are gzip-compressed NDJSON containing full game event logs.
Replays are public and served to any user via the lobby replay API.
Files are written with owner-only permissions (0o600) inside an
owner-only directory (0o700) as a filesystem hygiene measure.
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


class ReplayStorage(Protocol):
    """Protocol for persisting replay data."""

    def save_replay(self, game_id: str, content: str) -> None: ...


class LocalReplayStorage:
    """Writes gzip-compressed replay files to the local filesystem.

    Files are created with owner-only read/write (0o600) inside an
    owner-only directory (0o700) as a filesystem hygiene measure.
    """

    def __init__(self, replay_dir: str) -> None:
        self._replay_dir = Path(replay_dir).resolve()

    def save_replay(self, game_id: str, content: str) -> None:
        """Save gzip-compressed replay content under the configured directory.

        Creates the directory lazily on first write with owner-only permissions
        (0o700). Writes replay files atomically via temp-file-then-rename with
        owner-only permissions (0o600). Rejects path traversal attempts that
        would place the file outside the replay root.
        """
        target = (self._replay_dir / f"{game_id}.txt.gz").resolve()
        if not target.is_relative_to(self._replay_dir):
            raise ValueError(f"Path traversal rejected: '{game_id}' resolves outside replay directory")

        self._replay_dir.mkdir(mode=_REPLAY_DIR_MODE, parents=True, exist_ok=True)
        self._replay_dir.chmod(_REPLAY_DIR_MODE)

        compressed = gzip.compress(content.encode("utf-8"))

        fd, tmp_path = tempfile.mkstemp(dir=str(self._replay_dir), suffix=".tmp", prefix=".replay_")
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
