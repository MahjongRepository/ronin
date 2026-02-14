"""Tests for replay storage abstraction."""

import os
import stat
from unittest.mock import patch

import pytest

from shared.storage import LocalReplayStorage


class TestLocalReplayStorage:
    def test_creates_directory_on_first_write(self, tmp_path):
        replay_dir = tmp_path / "replays"
        storage = LocalReplayStorage(str(replay_dir))

        storage.save_replay("game_1", "line1\nline2\n")

        assert replay_dir.is_dir()
        assert (replay_dir / "game_1.txt").exists()

    def test_writes_correct_content(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))
        content = '{"type":"discard","target":"all"}\n{"type":"draw","target":"all"}\n'

        storage.save_replay("game_abc", content)

        written = (tmp_path / "game_abc.txt").read_text(encoding="utf-8")
        assert written == content

    def test_overwrites_existing_file(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))

        storage.save_replay("game_1", "original content")
        storage.save_replay("game_1", "updated content")

        written = (tmp_path / "game_1.txt").read_text(encoding="utf-8")
        assert written == "updated content"

    def test_rejects_path_traversal_with_dot_dot(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))

        with pytest.raises(ValueError, match="Path traversal rejected"):
            storage.save_replay("../escape", "malicious")

    def test_rejects_path_traversal_with_absolute_component(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))

        with pytest.raises(ValueError, match="Path traversal rejected"):
            storage.save_replay("../../etc/passwd", "malicious")

    def test_does_not_create_directory_on_traversal_rejection(self, tmp_path):
        replay_dir = tmp_path / "replays"
        storage = LocalReplayStorage(str(replay_dir))

        with pytest.raises(ValueError, match="Path traversal rejected"):
            storage.save_replay("../escape", "malicious")

        assert not replay_dir.exists()

    def test_writes_utf8_content(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))
        content = '{"player":"プレイヤー","type":"win"}\n'

        storage.save_replay("game_unicode", content)

        written = (tmp_path / "game_unicode.txt").read_text(encoding="utf-8")
        assert written == content

    def test_multiple_games_write_separate_files(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))

        storage.save_replay("game_1", "content_1")
        storage.save_replay("game_2", "content_2")

        assert (tmp_path / "game_1.txt").read_text() == "content_1"
        assert (tmp_path / "game_2.txt").read_text() == "content_2"


class TestLocalReplayStorageErrorHandling:
    """Tests for error handling during file write operations."""

    def test_save_replay_cleans_up_temp_on_fdopen_failure(self, tmp_path):
        """If os.fdopen fails, the temp file is removed and no target is created."""
        storage = LocalReplayStorage(str(tmp_path))

        with (
            patch("os.fdopen", side_effect=OSError("fdopen failure")),
            pytest.raises(OSError, match="fdopen failure"),
        ):
            storage.save_replay("game_fail", "content")

        # No target file or leftover temp files
        assert not (tmp_path / "game_fail.txt").exists()
        remaining = list(tmp_path.glob(".replay_*.tmp"))
        assert remaining == []

    def test_save_replay_cleans_up_temp_on_fsync_failure(self, tmp_path):
        """If fsync fails after write, the temp file is removed and no target is created."""
        storage = LocalReplayStorage(str(tmp_path))

        with (
            patch("os.fsync", side_effect=OSError("fsync failure")),
            pytest.raises(OSError, match="fsync failure"),
        ):
            storage.save_replay("game_fail", "content")

        assert not (tmp_path / "game_fail.txt").exists()
        remaining = list(tmp_path.glob(".replay_*.tmp"))
        assert remaining == []

    def test_save_replay_closes_fd_on_fdopen_failure(self, tmp_path):
        """If os.fdopen raises, the raw file descriptor is closed."""
        storage = LocalReplayStorage(str(tmp_path))

        with (
            patch("os.fdopen", side_effect=OSError("fdopen failure")) as mock_fdopen,
            patch("os.close", wraps=os.close) as mock_close,
            pytest.raises(OSError, match="fdopen failure"),
        ):
            storage.save_replay("game_fail", "content")

        # os.fdopen received the fd from mkstemp
        fd_arg = mock_fdopen.call_args[0][0]
        mock_close.assert_called_once_with(fd_arg)

    def test_no_double_close_when_fdopen_succeeds_but_fsync_fails(self, tmp_path):
        """After fdopen takes ownership, os.close(fd) must not be called in cleanup."""
        storage = LocalReplayStorage(str(tmp_path))

        with (
            patch("os.fsync", side_effect=OSError("fsync failure")),
            patch("os.close") as mock_close,
            pytest.raises(OSError, match="fsync failure"),
        ):
            storage.save_replay("game_fail", "content")

        # os.close should not be called because fdopen took fd ownership
        # and the context manager already closed it
        mock_close.assert_not_called()


class TestLocalReplayStoragePermissions:
    """Tests for replay file and directory permission restrictions."""

    def test_replay_directory_created_with_owner_only_permissions(self, tmp_path):
        replay_dir = tmp_path / "replays"
        storage = LocalReplayStorage(str(replay_dir))

        storage.save_replay("game_1", "content")

        dir_mode = stat.S_IMODE(replay_dir.stat().st_mode)
        assert dir_mode == 0o700

    def test_replay_file_created_with_owner_only_permissions(self, tmp_path):
        replay_dir = tmp_path / "replays"
        storage = LocalReplayStorage(str(replay_dir))

        storage.save_replay("game_1", "content")

        file_path = replay_dir / "game_1.txt"
        file_mode = stat.S_IMODE(file_path.stat().st_mode)
        assert file_mode == 0o600

    def test_overwritten_file_retains_owner_only_permissions(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))

        storage.save_replay("game_1", "first")
        storage.save_replay("game_1", "second")

        file_path = tmp_path / "game_1.txt"
        file_mode = stat.S_IMODE(file_path.stat().st_mode)
        assert file_mode == 0o600

    def test_replay_file_not_group_or_world_readable(self, tmp_path):
        storage = LocalReplayStorage(str(tmp_path))

        storage.save_replay("game_1", "sensitive data")

        file_path = tmp_path / "game_1.txt"
        file_mode = file_path.stat().st_mode
        # No group or other permissions
        assert not file_mode & stat.S_IRGRP
        assert not file_mode & stat.S_IWGRP
        assert not file_mode & stat.S_IROTH
        assert not file_mode & stat.S_IWOTH

    def test_replay_persistence_works_under_restricted_permissions(self, tmp_path):
        """Full round-trip: write and read back under restricted permissions."""
        replay_dir = tmp_path / "secure_replays"
        storage = LocalReplayStorage(str(replay_dir))
        content = '{"type":"draw","target":"seat_0","seat":0,"tile_id":42}'

        storage.save_replay("game_secure", content)

        written = (replay_dir / "game_secure.txt").read_text(encoding="utf-8")
        assert written == content
