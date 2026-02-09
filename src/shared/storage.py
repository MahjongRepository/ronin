"""Storage abstraction for replay persistence.

Replay files contain concealed game data (player hands, draw tiles, dora
indicators, winner details) and are treated as sensitive artifacts. Files
are written with owner-only permissions (0o600) inside an owner-only
directory (0o700) to prevent unintended access.
"""

import contextlib
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

# Owner-only directory permissions for replay storage.
_REPLAY_DIR_MODE = 0o700

# Owner-only file permissions for replay data files.
_REPLAY_FILE_MODE = 0o600


class ReplayStorage(Protocol):
    """Protocol for persisting replay data."""

    def save_replay(self, game_id: str, content: str) -> None: ...


class LocalReplayStorage:
    """Writes replay files to the local filesystem with restricted permissions.

    Replay data contains concealed game information (initial hands, draw tiles,
    dora indicators, winner hand details). Files are created with owner-only
    read/write (0o600) inside an owner-only directory (0o700).
    """

    def __init__(self, replay_dir: str) -> None:
        self._replay_dir = Path(replay_dir).resolve()

    def save_replay(self, game_id: str, content: str) -> None:
        """Save replay content as a text file under the configured directory.

        Creates the directory lazily on first write with owner-only permissions
        (0o700). Writes replay files atomically via temp-file-then-rename with
        owner-only permissions (0o600). Rejects path traversal attempts that
        would place the file outside the replay root.
        """
        target = (self._replay_dir / f"{game_id}.txt").resolve()
        if not target.is_relative_to(self._replay_dir):
            raise ValueError(f"Path traversal rejected: '{game_id}' resolves outside replay directory")

        os.makedirs(str(self._replay_dir), mode=_REPLAY_DIR_MODE, exist_ok=True)  # noqa: PTH103
        self._replay_dir.chmod(_REPLAY_DIR_MODE)

        fd, tmp_path = tempfile.mkstemp(dir=str(self._replay_dir), suffix=".tmp", prefix=".replay_")
        fd_owned = True
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd_owned = False  # os.fdopen took ownership; it will close fd
                f.write(content)
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
        logger.info("Saved replay for game %s to %s", game_id, target)

    def cleanup_old_replays(self, max_age_seconds: int) -> int:
        """Delete replay files older than max_age_seconds.

        Returns the number of files removed. Errors on individual files are
        logged and skipped so that one bad file does not block the rest.
        """
        if max_age_seconds <= 0:
            raise ValueError(f"max_age_seconds must be positive, got {max_age_seconds}")

        if not self._replay_dir.is_dir():
            return 0

        cutoff = time.time() - max_age_seconds
        removed = 0
        for entry in self._replay_dir.iterdir():
            try:
                if not entry.is_file() or entry.is_symlink() or entry.suffix != ".txt":
                    continue
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
            except OSError:
                logger.exception("Failed to remove old replay file %s", entry)
        if removed:
            logger.info("Cleaned up %d replay files older than %d seconds", removed, max_age_seconds)
        return removed
