from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path
from typing import Any

from game.logic.enums import AbortiveDrawType, GameAction, KanType, WireGameType
from game.logic.events import EventType
from game.logic.exceptions import UnsupportedSettingsError
from game.logic.rng import RNG_VERSION, seat_permutation, validate_seed_hex
from game.logic.settings import NUM_PLAYERS, TRIPLE_RON_COUNT, GameSettings, validate_settings
from game.logic.tiles import NUM_TILES
from game.replay.models import ReplayInput, ReplayInputEvent
from game.wire.compact import decode_discard
from game.wire.enums import WireRoundResultType
from game.wire.events import EVENT_TYPE_INT
from game.wire.replay_format import REPLAY_VERSION, decode_replay_settings
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
    """
    Raised when a replay file cannot be loaded or parsed.
    """


def _validate_version_tag(tag: dict[str, Any]) -> str:
    """
    Validate the version tag (first line of the replay file).

    Return the version string.
    """
    version = tag.get("version")
    if version is None:
        raise ReplayLoadError("First line must be a version tag with 'version' field")

    if version != REPLAY_VERSION:
        raise ReplayLoadError(f"Replay version mismatch: expected {REPLAY_VERSION}, got {version}")

    return version


def _validate_game_started(first: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Validate and extract fields from the game_started event.

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


def _parse_game_settings(first: dict[str, Any]) -> GameSettings:
    """
    Parse the game_started event's recorded settings (gs), which the engine must support and its game length (gt) must
    match.
    """
    try:
        settings = decode_replay_settings(first.get("gs"))
        validate_settings(settings)
    except (TypeError, ValueError, UnsupportedSettingsError) as exc:
        raise ReplayLoadError(f"game_started event has invalid settings (gs): {exc}") from exc

    game_type = first.get("gt")
    expected_game_type = WireGameType[settings.game_type.name]
    if not isinstance(game_type, int) or isinstance(game_type, bool) or game_type != expected_game_type:
        raise ReplayLoadError(
            f"game_started game type (gt) {game_type!r} does not match its settings' {expected_game_type.value}",
        )

    return settings


def _parse_event_lines(content: str) -> list[dict[str, Any]]:
    """
    Decode each non-blank line as a JSON object, naming the physical line of the first one that is not.
    """
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.split("\n"), start=1):
        if not line.strip():
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayLoadError(f"Malformed JSON: line {line_number}: {exc.msg}") from exc

        if not isinstance(event, dict):
            raise ReplayLoadError(f"Malformed JSON: line {line_number} is not an object, got {type(event).__name__}")

        events.append(event)

    return events


def load_replay_from_string(content: str) -> ReplayInput:
    """
    Parse newline-delimited JSON objects into ReplayInput.
    """
    if not content.strip():
        raise ReplayLoadError("Empty replay content")

    events = _parse_event_lines(content)
    if len(events) > _MAX_REPLAY_EVENTS:
        raise ReplayLoadError(f"Replay exceeds maximum event count ({_MAX_REPLAY_EVENTS})")

    if len(events) < _MIN_EVENT_COUNT:
        raise ReplayLoadError("Replay must contain at least a version tag and game_started event")

    _validate_version_tag(events[0])
    seed, rng_version, players = _validate_game_started(events[1])

    seat_to_name = _extract_seat_to_name(players)
    player_names = _reconstruct_input_order(seed, seat_to_name)
    settings = _parse_game_settings(events[1])

    actions: list[ReplayInputEvent] = []
    for event in events[2:]:
        extracted = _extract_action(event, seat_to_name)
        if extracted is not None:
            actions.extend(extracted)

    return ReplayInput(
        seed=seed,
        rng_version=rng_version,
        player_names=player_names,
        settings=settings,
        events=tuple(actions),
    )


def load_replay_from_file(path: str | Path) -> ReplayInput:
    """
    Load a replay from a file path.

    Supports both plain text and gzip-compressed (.gz) replay files.
    """
    path = Path(path)
    try:
        if path.name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                content = f.read()
        else:
            content = path.read_text(encoding="utf-8")
    except (OSError, EOFError, zlib.error) as exc:
        raise ReplayLoadError(f"Cannot read replay file {path}: {exc}") from exc

    return load_replay_from_string(content)


def _extract_seat_to_name(players: list[dict[str, Any]]) -> dict[int, str]:
    """
    Extract seat-to-name mapping from game_started players, validating structure.
    """
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
    """
    Reconstruct the original player name input order from the seed.

    During replay, fill_seats receives all 4 names (human + AI) and seats them by the seed's seat permutation. This
    function inverts that permutation: given the seed and the seat-to-name mapping, it produces the name ordering that,
    fed back through fill_seats with the same seed, recreates the original seating.
    """
    expected_seats = set(range(NUM_PLAYERS))
    if set(seat_to_name.keys()) != expected_seats:
        raise ReplayLoadError(
            f"game_started players must have exactly seats {expected_seats}, got: {set(seat_to_name.keys())}",
        )

    first, second, third, fourth = (seat_to_name[s] for s in seat_permutation(seed))
    return first, second, third, fourth


def _extract_action(
    event: dict[str, Any],
    seat_to_name: dict[int, str],
) -> list[ReplayInputEvent] | None:
    """
    Extract player action(s) from a single event-log entry.

    Return a list of ReplayInputEvent (usually one, two for double_ron), or None if the event does not represent a
    player action. Raise ReplayLoadError for unknown event types, so a new action-producing event fails loudly instead
    of being silently dropped from the replay.
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
    """
    Parse a discard event from packed integer encoding.
    """
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
    """
    Parse a compact meld event {"t": 0, "m": <IMME_int>} into a call action.
    """
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

    match meld_type:
        case "chi":
            return _parse_chi_from_meld_data(meld_data, player_name)
        case "pon":
            return _parse_pon_from_meld_data(meld_data, player_name)
        case "open_kan" | "closed_kan" | "added_kan":
            return _parse_kan_from_meld_data(meld_data, player_name)
        case _:
            raise ReplayLoadError(f"Unknown meld_type in decoded IMME: {meld_type!r}")


def _parse_chi_from_meld_data(meld_data: MeldData, player_name: str) -> ReplayInputEvent:
    """
    Parse a chi action from a decoded MeldData dict.
    """
    called_tile_id = meld_data["called_tile_id"]
    tile_ids = meld_data["tile_ids"]
    sequence_tiles = [t for t in tile_ids if t != called_tile_id]
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_CHI,
        data={"tile_id": called_tile_id, "sequence_tiles": sequence_tiles},
    )


def _parse_pon_from_meld_data(meld_data: MeldData, player_name: str) -> ReplayInputEvent:
    """
    Parse a pon action from a decoded MeldData dict.
    """
    called_tile_id = meld_data["called_tile_id"]
    return ReplayInputEvent(
        player_name=player_name,
        action=GameAction.CALL_PON,
        data={"tile_id": called_tile_id},
    )


def _parse_kan_from_meld_data(meld_data: MeldData, player_name: str) -> ReplayInputEvent:
    """
    Parse a kan action from a decoded MeldData dict.
    """
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
    """
    Parse a round_end event into player action(s), if any.
    """
    result_type = event.get("rt")
    can_rob_kan = result_type in (WireRoundResultType.RON, WireRoundResultType.DOUBLE_RON) or (
        result_type == WireRoundResultType.ABORTIVE_DRAW and event.get("rn") == AbortiveDrawType.TRIPLE_RON
    )
    if event.get("rk") is not None and not can_rob_kan:
        raise ReplayLoadError(f"round_end that robs no kan carries a robbed kan (rk): {event['rk']!r}")

    is_ron = result_type in (WireRoundResultType.RON, WireRoundResultType.DOUBLE_RON)
    if event.get("hbs") is not None and not is_ron:
        raise ReplayLoadError(f"round_end that is no ron carries head-bumped ron seats (hbs): {event['hbs']!r}")

    match result_type:
        case WireRoundResultType.TSUMO:
            return _parse_tsumo_round_end(event, seat_to_name)
        case WireRoundResultType.RON:
            return _parse_ron_round_end(event, seat_to_name)
        case WireRoundResultType.DOUBLE_RON:
            return _parse_double_ron_round_end(event, seat_to_name)
        case WireRoundResultType.ABORTIVE_DRAW:
            return _parse_abortive_draw_round_end(event, seat_to_name)
        # exhaustive_draw, nagashi_mangan — no player action
        case WireRoundResultType.EXHAUSTIVE_DRAW | WireRoundResultType.NAGASHI_MANGAN:
            return None
        case _:
            raise ReplayLoadError(f"Unknown round_end result type: {result_type!r}")


def _parse_tsumo_round_end(result: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent]:
    """
    Parse a tsumo round_end result.
    """
    player_name = _parse_seat_player(result.get("ws"), seat_to_name, field="tsumo round_end winner seat (ws)")
    return [ReplayInputEvent(player_name=player_name, action=GameAction.DECLARE_TSUMO)]


def _parse_ron_round_end(result: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent]:
    """
    Parse a ron round_end result.
    """
    player_name = _parse_seat_player(result.get("ws"), seat_to_name, field="ron round_end winner seat (ws)")
    return [
        *_parse_robbed_kan(result, seat_to_name),
        ReplayInputEvent(player_name=player_name, action=GameAction.CALL_RON),
        *_parse_head_bumped_rons(result, seat_to_name, winner_names={player_name}),
    ]


def _parse_double_ron_round_end(
    result: dict[str, Any],
    seat_to_name: dict[int, str],
) -> list[ReplayInputEvent]:
    """
    Parse a double_ron round_end result.
    """
    winners = result.get("wn")
    if not isinstance(winners, list) or not winners:
        raise ReplayLoadError(f"double_ron round_end must have a non-empty winner list (wn): {winners!r}")

    rons: list[ReplayInputEvent] = []
    for winner in winners:
        if not isinstance(winner, dict):
            raise ReplayLoadError(f"double_ron round_end winner must be an object, got {winner!r}")

        player_name = _parse_seat_player(winner.get("ws"), seat_to_name, field="double_ron round_end winner seat (ws)")
        rons.append(ReplayInputEvent(player_name=player_name, action=GameAction.CALL_RON))

    winner_names = {ron.player_name for ron in rons}
    return [
        *_parse_robbed_kan(result, seat_to_name),
        *rons,
        *_parse_head_bumped_rons(result, seat_to_name, winner_names=winner_names),
    ]


def _parse_abortive_draw_round_end(
    result: dict[str, Any],
    seat_to_name: dict[int, str],
) -> list[ReplayInputEvent] | None:
    """
    Parse an abortive_draw round_end result: the kyuushu kyuuhai declaration or each triple ron declaration.
    """
    reason = result.get("rn")
    if reason == AbortiveDrawType.TRIPLE_RON:
        return _parse_triple_ron_declarations(result, seat_to_name)

    if reason != AbortiveDrawType.NINE_TERMINALS:
        # Other abortive draws (four_riichi, etc.) are not player actions
        return None

    player_name = _parse_seat_player(result.get("s"), seat_to_name, field="nine_terminals abortive_draw seat (s)")
    return [ReplayInputEvent(player_name=player_name, action=GameAction.CALL_KYUUSHU)]


def _parse_triple_ron_declarations(
    result: dict[str, Any],
    seat_to_name: dict[int, str],
) -> list[ReplayInputEvent]:
    """
    Parse a triple_ron abortive_draw's declaring seats (rcl) into one CALL_RON per seat, in their recorded order.

    The seats must be TRIPLE_RON_COUNT distinct known seats; anything else is a malformed replay.
    """
    seats = result.get("rcl")
    if not isinstance(seats, list) or len(seats) != TRIPLE_RON_COUNT:
        raise ReplayLoadError(f"triple_ron abortive_draw has invalid ron seats (rcl): {seats!r}")

    player_names = [
        _parse_seat_player(seat, seat_to_name, field="triple_ron abortive_draw ron seat (rcl)") for seat in seats
    ]
    if len(set(player_names)) != len(player_names):
        raise ReplayLoadError(f"triple_ron abortive_draw has invalid ron seats (rcl): {seats!r}")

    rons = [ReplayInputEvent(player_name=name, action=GameAction.CALL_RON) for name in player_names]
    return [*_parse_robbed_kan(result, seat_to_name), *rons]


def _parse_robbed_kan(result: dict[str, Any], seat_to_name: dict[int, str]) -> list[ReplayInputEvent]:
    """
    Parse the kan a chankan robbed (rk) into the kan declaration that opened the chankan prompt, if the result has one.

    A robbed kan never completes, so no meld event records it: its ron or triple ron result carries it instead, and its
    declaration must precede the rons that answer it.
    """
    robbed_kan = result.get("rk")
    if robbed_kan is None:
        return []

    if not isinstance(robbed_kan, dict):
        raise ReplayLoadError(f"round_end has an invalid robbed kan (rk): {robbed_kan!r}")

    player_name = _parse_seat_player(robbed_kan.get("s"), seat_to_name, field="round_end robbed kan (rk) seat (s)")
    tile_id = robbed_kan.get("ti")
    kan_type = robbed_kan.get("kty")
    is_tile = isinstance(tile_id, int) and not isinstance(tile_id, bool) and 0 <= tile_id < NUM_TILES
    if not is_tile or kan_type not in (KanType.ADDED.value, KanType.CLOSED.value):
        raise ReplayLoadError(f"round_end has an invalid robbed kan (rk): {robbed_kan!r}")

    return [
        ReplayInputEvent(
            player_name=player_name,
            action=GameAction.CALL_KAN,
            data={"tile_id": tile_id, "kan_type": kan_type},
        ),
    ]


def _parse_head_bumped_rons(
    result: dict[str, Any],
    seat_to_name: dict[int, str],
    *,
    winner_names: set[str],
) -> list[ReplayInputEvent]:
    """
    Parse the seats whose declared ron lost to head bump (hbs) into their CALL_RON, after the winners' rons.

    The live game resolved its prompt with those declarations, so the replay must declare them too: a pass in their
    place would leave them temporarily furiten. Absent when no declaration was bumped; when present it must hold
    distinct known seats other than the winners, the discarder (ls) and a robbed kan's declarer.
    """
    seats = result.get("hbs")
    if seats is None:
        return []

    if not isinstance(seats, list) or not seats:
        raise ReplayLoadError(f"round_end has invalid head-bumped ron seats (hbs): {seats!r}")

    player_names = [
        _parse_seat_player(seat, seat_to_name, field="round_end head-bumped ron seat (hbs)") for seat in seats
    ]
    loser_name = _parse_seat_player(result.get("ls"), seat_to_name, field="round_end loser seat (ls)")
    kan_declarer_names = {kan.player_name for kan in _parse_robbed_kan(result, seat_to_name)}
    non_declarer_names = {*winner_names, loser_name, *kan_declarer_names}
    if len(set(player_names)) != len(player_names) or non_declarer_names & set(player_names):
        raise ReplayLoadError(f"round_end has invalid head-bumped ron seats (hbs): {seats!r}")

    return [ReplayInputEvent(player_name=name, action=GameAction.CALL_RON) for name in player_names]


def _parse_seat_player(seat: object, seat_to_name: dict[int, str], *, field: str) -> str:
    """
    Return the player at a round_end's seat field; a missing seat, or one that is not a known integer seat, is a
    malformed replay.
    """
    if not isinstance(seat, int) or isinstance(seat, bool) or seat not in seat_to_name:
        raise ReplayLoadError(f"{field} is not a known seat: {seat!r}")

    return seat_to_name[seat]
