"""Replay loader: parse ReplayCollector event-log format into ReplayInput.

The ReplayCollector writes gameplay events as concatenated JSON objects on a single line.
This module reads that format, extracts player actions from the event
stream, and constructs a validated ReplayInput for the replay runner.

Event types that represent player actions are mapped via an explicit allowlist.
Unknown event types raise ReplayLoadError to surface new action-producing
events rather than silently dropping them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from game.logic.enums import GameAction, WireRoundResultType
from game.logic.events import EventType
from game.logic.rng import RNG_VERSION, create_seat_rng, validate_seed_hex
from game.logic.settings import NUM_PLAYERS
from game.messaging.compact import decode_discard
from game.messaging.event_payload import EVENT_TYPE_INT
from game.replay.models import REPLAY_VERSION, ReplayInput, ReplayInputEvent
from shared.lib.melds import MeldData, decode_meld_compact

# Minimum number of events: version tag + game_started.
_MIN_EVENT_COUNT = 2

# Safety limit to prevent memory exhaustion from maliciously large replay files.
_MAX_REPLAY_EVENTS = 100_000

# Event types that do not represent player actions (skipped silently).
_NON_ACTION_EVENTS = frozenset(
    {
        EVENT_TYPE_INT[EventType.GAME_STARTED],
        EVENT_TYPE_INT[EventType.ROUND_STARTED],
        EVENT_TYPE_INT[EventType.DRAW],
        EVENT_TYPE_INT[EventType.DORA_REVEALED],
        EVENT_TYPE_INT[EventType.RIICHI_DECLARED],
        EVENT_TYPE_INT[EventType.GAME_END],
    },
)


class ReplayLoadError(Exception):
    """Raised when a replay file cannot be loaded or parsed."""


def _validate_version_tag(tag: dict[str, Any]) -> str:
    """Validate the version tag (first line of the replay file).

    Return the version string.
    """
    version = tag.get("version")
    if version is None:
        raise ReplayLoadError("First line must be a version tag with 'version' field")
    if version != REPLAY_VERSION:
        raise ReplayLoadError(f"Replay version mismatch: expected {REPLAY_VERSION}, got {version}")
    return version


def _validate_game_started(first: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    """Validate and extract fields from the game_started event.

    Returns (seed, rng_version, players).
    """
    if first.get("t") != EVENT_TYPE_INT[EventType.GAME_STARTED]:
        raise ReplayLoadError(f"First event must be game_started, got: {first.get('t')}")

    seed = first.get("sd")
    if seed is None:
        raise ReplayLoadError("game_started event missing 'sd' field")

    rng_version = first.get("rv")
    if rng_version is None:
        raise ReplayLoadError(
            "game_started event missing 'rv' field (old replay format not supported)",
        )
    if rng_version != RNG_VERSION:
        raise ReplayLoadError(f"Replay RNG version mismatch: expected {RNG_VERSION}, got {rng_version}")

    try:
        validate_seed_hex(seed)
    except (ValueError, TypeError) as exc:
        raise ReplayLoadError(f"game_started event has invalid seed: {exc}") from exc

    players = first.get("p")
    if not players or not isinstance(players, list):
        raise ReplayLoadError("game_started event missing 'p' field")

    return seed, rng_version, players


def load_replay_from_string(content: str) -> ReplayInput:
    """Parse concatenated JSON objects (split on '}{') into ReplayInput."""
    content = content.strip()
    if not content:
        raise ReplayLoadError("Empty replay content")

    try:
        events = json.loads("[" + content.replace("}{", "},{") + "]")
    except json.JSONDecodeError as exc:
        raise ReplayLoadError(f"Malformed JSON: {exc}") from exc

    if len(events) > _MAX_REPLAY_EVENTS:
        raise ReplayLoadError(f"Replay exceeds maximum event count ({_MAX_REPLAY_EVENTS})")

    if len(events) < _MIN_EVENT_COUNT:
        raise ReplayLoadError("Replay must contain at least a version tag and game_started event")

    _validate_version_tag(events[0])
    seed, rng_version, players = _validate_game_started(events[1])

    seat_to_name = _extract_seat_to_name(players)
    player_names = _reconstruct_input_order(seed, seat_to_name)

    actions: list[ReplayInputEvent] = []
    for event in events[2:]:
        extracted = _extract_action(event, seat_to_name)
        if extracted is not None:
            actions.extend(extracted)

    return ReplayInput(
        seed=seed,
        rng_version=rng_version,
        player_names=player_names,
        events=tuple(actions),
    )


def load_replay_from_file(path: str | Path) -> ReplayInput:
    """Load a replay from a file path."""
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReplayLoadError(f"Cannot read replay file {path}: {exc}") from exc
    return load_replay_from_string(content)


def _extract_seat_to_name(players: list[dict[str, Any]]) -> dict[int, str]:
    """Extract seat-to-name mapping from game_started players, validating structure."""
    seat_to_name: dict[int, str] = {}
    for i, player in enumerate(players):
        if not isinstance(player, dict):
            raise ReplayLoadError(f"game_started player entry {i} is not a dict")
        try:
            seat = player["s"]
            name = player["nm"]
        except KeyError as exc:
            raise ReplayLoadError(f"game_started player entry {i} missing required field: {exc}") from exc
        if not isinstance(seat, int):
            raise ReplayLoadError(f"game_started player entry {i} has non-integer seat: {seat!r}")
        if not isinstance(name, str) or not name:
            raise ReplayLoadError(f"game_started player entry {i} has invalid name: {name!r}")
        seat_to_name[seat] = name
    return seat_to_name


def _reconstruct_input_order(
    seed: str,
    seat_to_name: dict[int, str],
) -> tuple[str, str, str, str]:
    """Reconstruct the original player name input order from the seed.

    During replay, fill_seats receives all 4 names (human + AI) and calls
    rng.sample(range(4), 4) to assign seats. This function inverts that
    permutation: given the seed and the seat-to-name mapping, it produces
    the name ordering that, when fed back through fill_seats with the same
    seed, recreates the original seating.
    """
    expected_seats = set(range(NUM_PLAYERS))
    if set(seat_to_name.keys()) != expected_seats:
        raise ReplayLoadError(
            f"game_started players must have exactly seats {expected_seats}, got: {set(seat_to_name.keys())}",
        )
    rng = create_seat_rng(seed)
    seat_order = rng.sample(range(NUM_PLAYERS), NUM_PLAYERS)
    return tuple(seat_to_name[s] for s in seat_order)  # type: ignore[return-value]


def _extract_action(
    event: dict[str, Any],
    seat_to_name: dict[int, str],
) -> list[ReplayInputEvent] | None:
    """Extract player action(s) from a single event-log entry.

    Return a list of ReplayInputEvent (usually one, two for double_ron),
    or None if the event does not represent a player action.
    Raise ReplayLoadError for unknown event types.
    """
    event_type = event.get("t")
    if event_type is None:
        raise ReplayLoadError("Event missing required 't' field")
    if not isinstance(event_type, int) or isinstance(event_type, bool):
        raise ReplayLoadError(f"Event 't' field must be an integer, got {type(event_type).__name__}")

    if event_type in _NON_ACTION_EVENTS:
        return None

    if event_type == EVENT_TYPE_INT[EventType.DISCARD]:
        return [_parse_discard(event, seat_to_name)]

    if event_type == EVENT_TYPE_INT[EventType.MELD]:
        return [_parse_meld_compact(event, seat_to_name)]

    if event_type == EVENT_TYPE_INT[EventType.ROUND_END]:
        return _parse_round_end(event, seat_to_name)

    raise ReplayLoadError(f"Unknown event type: {event_type!r}")


def _parse_discard(event: dict[str, Any], seat_to_name: dict[int, str]) -> ReplayInputEvent:
    """Parse a discard event from packed integer encoding."""
    d = event.get("d")
    if d is None:
        raise ReplayLoadError("discard event missing 'd' field")
    try:
        seat, tile_id, _is_tsumogiri, is_riichi = decode_discard(d)
    except (ValueError, TypeError) as exc:
        raise ReplayLoadError(f"Invalid discard packed value: {exc}") from exc
    action = GameAction.DECLARE_RIICHI if is_riichi else GameAction.DISCARD
    try:
        player_name = seat_to_name[seat]
    except KeyError:
        raise ReplayLoadError(f"discard event references unknown seat: {seat}") from None
    return ReplayInputEvent(
        player_name=player_name,
        action=action,
        data={"tile_id": tile_id},
    )


def _parse_meld_compact(event: dict[str, Any], seat_to_name: dict[int, str]) -> ReplayInputEvent:
    """Parse a compact meld event {"t": 0, "m": <IMME_int>} into a call action."""
    imme_value = event.get("m")
    if imme_value is None:
        raise ReplayLoadError("Compact meld event missing 'm' field")
    if not isinstance(imme_value, int) or isinstance(imme_value, bool):
        raise ReplayLoadError(f"Compact meld 'm' field must be an integer, got {type(imme_value).__name__}")

    try:
        meld_data = decode_meld_compact(imme_value)
    except (ValueError, TypeError) as exc:
        raise ReplayLoadError(f"Invalid compact meld value {imme_value}: {exc}") from exc
    caller_seat = meld_data["caller_seat"]
    meld_type = meld_data["meld_type"]

    try:
        player_name = seat_to_name[caller_seat]
    except KeyError:
        raise ReplayLoadError(f"meld event references unknown seat: {caller_seat}") from None

    if meld_type == "chi":
        return _parse_chi_from_meld_data(meld_data, player_name)
    if meld_type == "pon":
        return _parse_pon_from_meld_data(meld_data, player_name)
    if meld_type in ("open_kan", "closed_kan", "added_kan"):
        return _parse_kan_from_meld_data(meld_data, player_name)
    raise ReplayLoadError(f"Unknown meld_type in decoded IMME: {meld_type!r}")


def _parse_chi_from_meld_data(meld_data: MeldData, player_name: str) -> ReplayInputEvent:
    """Parse a chi action from a decoded MeldData dict."""
    called_tile_id = meld_data["called_tile_id"]
    tile_ids = meld_data["tile_ids"]
    sequence_tiles = [t for t in tile_ids if t != called_tile_id]
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_CHI,
        data={"tile_id": called_tile_id, "sequence_tiles": sequence_tiles},
    )


def _parse_pon_from_meld_data(meld_data: MeldData, player_name: str) -> ReplayInputEvent:
    """Parse a pon action from a decoded MeldData dict."""
    called_tile_id = meld_data["called_tile_id"]
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_PON,
        data={"tile_id": called_tile_id},
    )


def _parse_kan_from_meld_data(meld_data: MeldData, player_name: str) -> ReplayInputEvent:
    """Parse a kan action from a decoded MeldData dict."""
    meld_type = meld_data["meld_type"]
    kan_type_map = {"open_kan": "open", "closed_kan": "closed", "added_kan": "added"}
    kan_type = kan_type_map[meld_type]

    tile_ids = meld_data["tile_ids"]
    called_tile_id = meld_data["called_tile_id"]

    tile_id = called_tile_id if called_tile_id is not None else tile_ids[0]

    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_KAN,
        data={"tile_id": tile_id, "kan_type": kan_type},
    )


def _parse_round_end(event: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent] | None:
    """Parse a round_end event into player action(s), if any."""
    result_type = event.get("rt")

    if result_type == WireRoundResultType.TSUMO:
        return _parse_tsumo_round_end(event, seat_to_name)
    if result_type == WireRoundResultType.RON:
        return _parse_ron_round_end(event, seat_to_name)
    if result_type == WireRoundResultType.DOUBLE_RON:
        return _parse_double_ron_round_end(event, seat_to_name)
    if result_type == WireRoundResultType.ABORTIVE_DRAW:
        return _parse_abortive_draw_round_end(event, seat_to_name)
    # exhaustive_draw, nagashi_mangan — no player action
    if result_type in (WireRoundResultType.EXHAUSTIVE_DRAW, WireRoundResultType.NAGASHI_MANGAN):
        return None
    raise ReplayLoadError(f"Unknown round_end result type: {result_type!r}")


def _parse_tsumo_round_end(result: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent]:
    """Parse a tsumo round_end result."""
    try:
        winner_seat = result["ws"]
        player_name = seat_to_name[winner_seat]
    except KeyError as exc:
        raise ReplayLoadError(f"tsumo round_end missing or invalid field: {exc}") from exc
    return [ReplayInputEvent(player_name=player_name, action=GameAction.DECLARE_TSUMO)]


def _parse_ron_round_end(result: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent]:
    """Parse a ron round_end result."""
    try:
        winner_seat = result["ws"]
        player_name = seat_to_name[winner_seat]
    except KeyError as exc:
        raise ReplayLoadError(f"ron round_end missing or invalid field: {exc}") from exc
    return [ReplayInputEvent(player_name=player_name, action=GameAction.CALL_RON)]


def _parse_double_ron_round_end(
    result: dict[str, Any],
    seat_to_name: dict[int, str],
) -> list[ReplayInputEvent]:
    """Parse a double_ron round_end result."""
    winners = result.get("wn", [])
    if not winners:
        raise ReplayLoadError("double_ron round_end must have at least one winner")
    try:
        return [
            ReplayInputEvent(
                player_name=seat_to_name[w["ws"]],
                action=GameAction.CALL_RON,
            )
            for w in winners
        ]
    except KeyError as exc:
        raise ReplayLoadError(f"double_ron round_end missing or invalid field: {exc}") from exc


def _parse_abortive_draw_round_end(
    result: dict[str, Any],
    seat_to_name: dict[int, str],
) -> list[ReplayInputEvent] | None:
    """Parse an abortive_draw round_end result."""
    reason = result.get("rn")
    if reason != "nine_terminals":
        # Other abortive draws (four_riichi, etc.) are not player actions
        return None
    try:
        seat = result["s"]
        player_name = seat_to_name[seat]
    except KeyError as exc:
        raise ReplayLoadError(f"nine_terminals abortive_draw missing or invalid field: {exc}") from exc
    return [ReplayInputEvent(player_name=player_name, action=GameAction.CALL_KYUUSHU)]
