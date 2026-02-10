"""Replay loader: parse ReplayCollector event-log format into ReplayInput.

The ReplayCollector writes gameplay events as JSON Lines (one JSON object per
line). This module reads that format, extracts player actions from the event
stream, and constructs a validated ReplayInput for the replay runner.

Event types that represent player actions are mapped via an explicit allowlist.
Unknown event types raise ReplayLoadError to surface new action-producing
events rather than silently dropping them.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from game.logic.enums import GameAction
from game.replay.models import REQUIRED_PLAYER_COUNT, ReplayInput, ReplayInputEvent

# Event types that do not represent player actions (skipped silently).
_NON_ACTION_EVENTS = frozenset(
    {
        "game_started",
        "round_started",
        "draw",
        "dora_revealed",
        "riichi_declared",
        "game_end",
    }
)


class ReplayLoadError(Exception):
    """Raised when a replay file cannot be loaded or parsed."""


def load_replay_from_string(content: str) -> ReplayInput:
    """Parse ReplayCollector event-log format (JSON Lines) into ReplayInput."""
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        raise ReplayLoadError("Empty replay content")

    events: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ReplayLoadError(f"Malformed JSON on line {i + 1}: {exc}") from exc

    first = events[0]
    if first.get("type") != "game_started":
        raise ReplayLoadError(f"First event must be game_started, got: {first.get('type')}")

    seed = first.get("seed")
    if seed is None:
        raise ReplayLoadError("game_started event missing 'seed' field")

    players = first.get("players")
    if not players or not isinstance(players, list):
        raise ReplayLoadError("game_started event missing 'players' field")

    seat_to_name: dict[int, str] = {p["seat"]: p["name"] for p in players}
    player_names = _reconstruct_input_order(seed, seat_to_name)

    actions: list[ReplayInputEvent] = []
    for event in events[1:]:
        extracted = _extract_action(event, seat_to_name)
        if extracted is not None:
            actions.extend(extracted)

    return ReplayInput(
        seed=seed,
        player_names=player_names,  # type: ignore[arg-type]
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


def _reconstruct_input_order(
    seed: float,
    seat_to_name: dict[int, str],
) -> tuple[str, str, str, str]:
    """Reconstruct the original player name input order from the seed.

    The game service uses fill_seats(names, seed) which internally calls
    rng.sample(range(4), 4) to determine which seat each input name gets.
    Given the seed and the seat-to-name mapping, invert the permutation to
    recover the original input order so replaying produces identical seating.
    """
    expected_seats = set(range(REQUIRED_PLAYER_COUNT))
    if set(seat_to_name.keys()) != expected_seats:
        raise ReplayLoadError(
            f"game_started players must have exactly seats {expected_seats}, got: {set(seat_to_name.keys())}"
        )
    rng = random.Random(seed)  # noqa: S311
    seat_order = rng.sample(range(REQUIRED_PLAYER_COUNT), REQUIRED_PLAYER_COUNT)
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
    event_type = event.get("type")

    if event_type in _NON_ACTION_EVENTS:
        return None

    if event_type == "discard":
        return [_parse_discard(event, seat_to_name)]

    if event_type == "meld":
        return [_parse_meld(event, seat_to_name)]

    if event_type == "round_end":
        return _parse_round_end(event, seat_to_name)

    raise ReplayLoadError(f"Unknown event type: {event_type!r}")


def _parse_discard(event: dict[str, Any], seat_to_name: dict[int, str]) -> ReplayInputEvent:
    """Parse a discard event into a DISCARD or DECLARE_RIICHI action."""
    try:
        seat = event["seat"]
        tile_id = event["tile_id"]
    except KeyError as exc:
        raise ReplayLoadError(f"discard event missing required field: {exc}") from exc
    is_riichi = event.get("is_riichi", False)

    action = GameAction.DECLARE_RIICHI if is_riichi else GameAction.DISCARD
    try:
        player_name = seat_to_name[seat]
    except KeyError:  # pragma: no cover
        raise ReplayLoadError(f"discard event references unknown seat: {seat}") from None
    return ReplayInputEvent(
        player_name=player_name,
        action=action,
        data={"tile_id": tile_id},
    )


def _parse_meld(event: dict[str, Any], seat_to_name: dict[int, str]) -> ReplayInputEvent:
    """Parse a meld event into the corresponding call action."""
    meld_type = event.get("meld_type")
    try:
        caller_seat = event["caller_seat"]
    except KeyError as exc:
        raise ReplayLoadError(f"meld event missing required field: {exc}") from exc
    try:
        player_name = seat_to_name[caller_seat]
    except KeyError:  # pragma: no cover
        raise ReplayLoadError(f"meld event references unknown seat: {caller_seat}") from None

    if meld_type == "chi":
        return _parse_chi_meld(event, player_name)
    if meld_type == "pon":
        return _parse_pon_meld(event, player_name)
    if meld_type == "kan":
        return _parse_kan_meld(event, player_name)
    if meld_type == "shouminkan":
        return _parse_shouminkan_meld(event, player_name)
    raise ReplayLoadError(f"Unknown meld_type: {meld_type!r}")


def _parse_chi_meld(event: dict[str, Any], player_name: str) -> ReplayInputEvent:
    """Parse a chi meld event."""
    try:
        called_tile_id = event["called_tile_id"]
    except KeyError as exc:  # pragma: no cover
        raise ReplayLoadError(f"chi meld event missing required field: {exc}") from exc
    tile_ids = event.get("tile_ids", [])
    sequence_tiles = [t for t in tile_ids if t != called_tile_id]
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_CHI,
        data={"tile_id": called_tile_id, "sequence_tiles": sequence_tiles},
    )


def _parse_pon_meld(event: dict[str, Any], player_name: str) -> ReplayInputEvent:
    """Parse a pon meld event."""
    try:
        called_tile_id = event["called_tile_id"]
    except KeyError as exc:  # pragma: no cover
        raise ReplayLoadError(f"pon meld event missing required field: {exc}") from exc
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_PON,
        data={"tile_id": called_tile_id},
    )


def _parse_kan_meld(event: dict[str, Any], player_name: str) -> ReplayInputEvent:
    """Parse a kan meld event."""
    kan_type = event.get("kan_type")
    tile_ids = event.get("tile_ids", [])
    if tile_ids:
        tile_id = tile_ids[0]
    elif "called_tile_id" in event:
        tile_id = event["called_tile_id"]
    else:  # pragma: no cover
        raise ReplayLoadError("kan meld event missing both 'tile_ids' and 'called_tile_id'")
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_KAN,
        data={"tile_id": tile_id, "kan_type": kan_type},
    )


def _parse_shouminkan_meld(event: dict[str, Any], player_name: str) -> ReplayInputEvent:
    """Parse a shouminkan (added kan) meld event."""
    try:
        called_tile_id = event["called_tile_id"]
    except KeyError as exc:  # pragma: no cover
        raise ReplayLoadError(f"shouminkan meld event missing required field: {exc}") from exc
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_KAN,
        data={"tile_id": called_tile_id, "kan_type": "added"},
    )


def _parse_round_end(event: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent] | None:
    """Parse a round_end event into player action(s), if any."""
    result = event.get("result", {})
    result_type = result.get("type")

    if result_type == "tsumo":
        return _parse_tsumo_round_end(result, seat_to_name)
    if result_type == "ron":
        return _parse_ron_round_end(result, seat_to_name)
    if result_type == "double_ron":
        return _parse_double_ron_round_end(result, seat_to_name)
    if result_type == "abortive_draw":
        return _parse_abortive_draw_round_end(result, seat_to_name)
    # exhaustive_draw, nagashi_mangan — no player action
    if result_type in ("exhaustive_draw", "nagashi_mangan"):
        return None
    raise ReplayLoadError(f"Unknown round_end result type: {result_type!r}")


def _parse_tsumo_round_end(result: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent]:
    """Parse a tsumo round_end result."""
    try:
        winner_seat = result["winner_seat"]
        player_name = seat_to_name[winner_seat]
    except KeyError as exc:
        raise ReplayLoadError(f"tsumo round_end missing or invalid field: {exc}") from exc
    return [ReplayInputEvent(player_name=player_name, action=GameAction.DECLARE_TSUMO)]


def _parse_ron_round_end(result: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent]:
    """Parse a ron round_end result."""
    try:
        winner_seat = result["winner_seat"]
        player_name = seat_to_name[winner_seat]
    except KeyError as exc:  # pragma: no cover
        raise ReplayLoadError(f"ron round_end missing or invalid field: {exc}") from exc
    return [ReplayInputEvent(player_name=player_name, action=GameAction.CALL_RON)]


def _parse_double_ron_round_end(
    result: dict[str, Any], seat_to_name: dict[int, str]
) -> list[ReplayInputEvent]:
    """Parse a double_ron round_end result."""
    winners = result.get("winners", [])
    try:
        return [
            ReplayInputEvent(
                player_name=seat_to_name[w["winner_seat"]],
                action=GameAction.CALL_RON,
            )
            for w in winners
        ]
    except KeyError as exc:  # pragma: no cover
        raise ReplayLoadError(f"double_ron round_end missing or invalid field: {exc}") from exc


def _parse_abortive_draw_round_end(
    result: dict[str, Any], seat_to_name: dict[int, str]
) -> list[ReplayInputEvent] | None:
    """Parse an abortive_draw round_end result."""
    reason = result.get("reason")
    if reason != "nine_terminals":
        # Other abortive draws (four_riichi, etc.) are not player actions
        return None
    try:
        seat = result["seat"]
        player_name = seat_to_name[seat]
    except KeyError as exc:  # pragma: no cover
        raise ReplayLoadError(f"nine_terminals abortive_draw missing or invalid field: {exc}") from exc
    return [ReplayInputEvent(player_name=player_name, action=GameAction.CALL_KYUUSHU)]
