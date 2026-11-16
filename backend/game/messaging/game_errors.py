from __future__ import annotations

from enum import StrEnum
from typing import Literal

from game.engine import (
    Action,
    Chi,
    Discard,
    EventType,
    GameEvent,
    Kan,
    KanType,
    Pass,
    Pon,
    Refusal,
    RefusalCode,
    RefusalKind,
    Riichi,
    Ron,
    SeatTarget,
)


class GameErrorCode(StrEnum):
    """
    Error codes of an ErrorEvent: the game action was refused and nothing changed.
    """

    NOT_YOUR_TURN = "not_your_turn"
    INVALID_DISCARD = "invalid_discard"
    INVALID_RIICHI = "invalid_riichi"
    INVALID_RON = "invalid_ron"
    INVALID_PON = "invalid_pon"
    INVALID_CHI = "invalid_chi"
    INVALID_KAN = "invalid_kan"
    INVALID_PASS = "invalid_pass"  # noqa: S105
    INVALID_ACTION = "invalid_action"
    STALE_ACTION = "stale_action"


class ErrorEvent(GameEvent):
    """
    Event sent to a seat whose game action was refused.

    It names the wait id the refused action echoed (`wait_id`), so the client matches the refusal to its own request.
    """

    type: Literal[EventType.ERROR] = EventType.ERROR
    code: GameErrorCode
    message: str
    wait_id: int | None = None


_INVALID_CODES: dict[type[Action], GameErrorCode] = {
    Discard: GameErrorCode.INVALID_DISCARD,
    Riichi: GameErrorCode.INVALID_RIICHI,
    Ron: GameErrorCode.INVALID_RON,
    Pon: GameErrorCode.INVALID_PON,
    Chi: GameErrorCode.INVALID_CHI,
    Kan: GameErrorCode.INVALID_KAN,
    Pass: GameErrorCode.INVALID_PASS,
}

_ILLEGAL_DISCARD_MESSAGE = "tile {tile} is not a legal discard (kuikae or riichi tsumogiri)"

_RULE_ERRORS: dict[RefusalCode, tuple[GameErrorCode, str]] = {
    RefusalCode.KUIKAE: (GameErrorCode.INVALID_DISCARD, _ILLEGAL_DISCARD_MESSAGE),
    RefusalCode.RIICHI_DRAWN_TILE_ONLY: (GameErrorCode.INVALID_DISCARD, _ILLEGAL_DISCARD_MESSAGE),
    RefusalCode.RIICHI_BREAKS_TENPAI: (GameErrorCode.INVALID_RIICHI, "hand is not tenpai after discarding tile {tile}"),
}


def _answers_a_call(action: Action) -> bool:
    if isinstance(action, Kan):
        return action.kan_type == KanType.OPEN

    return isinstance(action, Ron | Pon | Chi | Pass)


def _refusal_code_and_message(action: Action, refusal: Refusal) -> tuple[GameErrorCode, str]:
    """
    Return the wire code and message of an action's refusal: the round not in play, a seat the action does not await
    (out of turn for a turn action, no call prompt for a call answer or pass), or a rule judgment on a discard.
    """
    if refusal.code == RefusalCode.WRONG_PHASE:
        return GameErrorCode.INVALID_ACTION, "round is not in progress"

    if refusal.kind == RefusalKind.NOT_AWAITED:
        if _answers_a_call(action):
            return _INVALID_CODES[type(action)], "no pending call prompt"

        return GameErrorCode.NOT_YOUR_TURN, "not your turn"

    rule_error = _RULE_ERRORS.get(refusal.code)
    if refusal.kind != RefusalKind.RULE or rule_error is None or not isinstance(action, Discard | Riichi):
        raise AssertionError(f"{action} refused as {refusal} has no game error")

    code, message = rule_error
    return code, message.format(tile=action.tile)


def refusal_error_event(action: Action, refusal: Refusal, *, seat: int, wait_id: int) -> ErrorEvent:
    """
    Build the ErrorEvent answering a seat's action the engine refused by rule or as not awaited, named by the wait id
    the action echoed.
    """
    code, message = _refusal_code_and_message(action, refusal)
    return ErrorEvent(code=code, message=message, target=SeatTarget(seat=seat), wait_id=wait_id)


def called_tile_mismatch_event(action: Action, *, seat: int, wait_id: int) -> ErrorEvent:
    """
    Build the ErrorEvent answering a call answer whose called tile is not the open call's: the answer's invalid code.
    """
    return ErrorEvent(
        code=_INVALID_CODES[type(action)],
        message="tile_id mismatch",
        target=SeatTarget(seat=seat),
        wait_id=wait_id,
    )


def stale_action_event(*, seat: int, wait_id: int) -> ErrorEvent:
    """
    Build the ErrorEvent answering an action, or a confirmation, for a decision that is not the seat's current one.
    """
    return ErrorEvent(
        code=GameErrorCode.STALE_ACTION,
        message="the wait this action answers has already ended",
        target=SeatTarget(seat=seat),
        wait_id=wait_id,
    )
