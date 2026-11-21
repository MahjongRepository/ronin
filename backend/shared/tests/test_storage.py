from pathlib import Path

import pytest

from shared.storage import replay_file_path


class TestReplayFilePath:
    def test_replay_file_path__when_uuid_game_id__should_return_two_level_sharded_path(self):
        base = Path("/replays")
        result = replay_file_path(base, "55ae1889-2f92-4007-9b66-baa11b0e6f05")
        assert result == base / "55" / "ae" / "55ae1889-2f92-4007-9b66-baa11b0e6f05.msgpack.gz"

    def test_replay_file_path__when_game_id_shorter_than_4_chars__should_raise(self):
        base = Path("/replays")
        with pytest.raises(ValueError, match="at least 4 characters"):
            replay_file_path(base, "abc")

    def test_replay_file_path__when_game_id_is_4_chars__should_accept(self):
        base = Path("/replays")
        result = replay_file_path(base, "abcd")
        assert result == base / "ab" / "cd" / "abcd.msgpack.gz"
