import re
from pathlib import Path

# Game IDs shorter than this cannot produce a two-level shard prefix.
MIN_GAME_ID_LENGTH = 4

_MAX_GAME_ID_LENGTH = 50
_GAME_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_REPLAY_FILE_SIZE = 1_048_576


def is_valid_game_id(game_id: str) -> bool:
    """
    Check that game_id can name a stored replay: alphanumeric with hyphens/underscores, 4 to 50 characters.
    """
    return MIN_GAME_ID_LENGTH <= len(game_id) <= _MAX_GAME_ID_LENGTH and _GAME_ID_PATTERN.match(game_id) is not None


def read_replay(replay_dir: str, game_id: str) -> bytes | None:
    """
    Read a stored replay's gzip-compressed bytes.

    Return None if game_id is invalid, the file is missing, unreadable or too large, or it resolves outside the replay
    directory.
    """
    if not is_valid_game_id(game_id):
        return None

    root = Path(replay_dir).resolve()
    target = replay_file_path(root, game_id).resolve()
    if not target.is_relative_to(root):
        return None

    try:
        with target.open("rb") as f:
            data = f.read(_MAX_REPLAY_FILE_SIZE + 1)
    except OSError:
        return None

    if len(data) > _MAX_REPLAY_FILE_SIZE:
        return None

    return data


def replay_file_path(replay_dir: Path, game_id: str) -> Path:
    """
    Build the sharded file path for a replay.

    Use the first 4 characters of game_id as a two-level directory prefix (2 chars each) to distribute files across
    subdirectories. Require game_id to be at least 4 characters long.
    """
    if len(game_id) < MIN_GAME_ID_LENGTH:
        raise ValueError(f"game_id must be at least {MIN_GAME_ID_LENGTH} characters, got {len(game_id)}")

    prefix_a = game_id[:2]
    prefix_b = game_id[2:4]
    return replay_dir / prefix_a / prefix_b / f"{game_id}.msgpack.gz"
