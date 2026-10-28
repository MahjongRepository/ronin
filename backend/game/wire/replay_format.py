import json
from enum import IntEnum
from typing import Any

from game.logic.settings import GameSettings
from game.wire.enums import WireEventType

REPLAY_VERSION = "0.3-dev"


class ReplayLineType(IntEnum):
    """
    Integer `t` of a replay-only line: an annotation the session writes beside the recorded events, never sent live.

    Its values share the `t` space with WireEventType and never take one of its values.
    """

    TIMEOUT = 100
    SEAT_CONTROL = 101


class ReplayTimeoutKind(IntEnum):
    """
    Integer `k` of a timeout line: the wait the seat let run out.
    """

    TURN = 0
    CALL = 1


class ReplaySeatControlReason(IntEnum):
    """
    Integer `r` of a seat control line that replaces a seat's human with an AI player: why its participant is not
    playing it.

    LEFT is a disconnect (a kick included) during play; ABSENT a participant without a connection at the first deal,
    never joined or gone during the game start pause.
    """

    LEFT = 0
    ABSENT = 1


if {int(line_type) for line_type in ReplayLineType} & {int(event_type) for event_type in WireEventType}:
    raise RuntimeError(  # pragma: no cover (exhaustive)
        f"ReplayLineType values {list(ReplayLineType)} overlap WireEventType values {list(WireEventType)}",
    )


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
