import json
from typing import Any

from game.logic.settings import GameSettings

REPLAY_VERSION = "0.3-dev"


def encode_replay_settings(settings: GameSettings) -> dict[str, Any]:
    """
    Encode a game's settings for its replay's game_started line.

    Every field is written, defaults included, so a replay never depends on the defaults of the code that loads it.
    """
    return settings.model_dump(mode="json")


def decode_replay_settings(raw: object) -> GameSettings:
    """
    Decode a replay's recorded settings: an object with exactly the GameSettings fields, each in its JSON type.

    Raise TypeError for a value that is no object and ValueError for any other mismatch; a missing field is an error,
    never a default.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"settings must be an object, got {type(raw).__name__}")

    missing = GameSettings.model_fields.keys() - raw.keys()
    if missing:
        raise ValueError(f"settings miss fields: {sorted(missing)}")

    return GameSettings.model_validate_json(json.dumps(raw), strict=True)
