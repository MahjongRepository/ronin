"""
Bot controller as a pure decision-maker.

Provides bot identification and decision methods.
Orchestration is handled by MahjongGameService.
"""

from typing import Any

from game.logic.bot import (
    BotPlayer,
    get_bot_action,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_ron,
)
from game.logic.enums import CallType, GameAction, KanType, MeldCallType, PlayerAction
from game.logic.state import (
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.types import MeldCaller


class BotController:
    """
    Decision-maker for bot players.

    Provides methods to check bot identity and get bot decisions
    for turn actions and call responses. Does not orchestrate game flow.
    """

    def __init__(self, bots: dict[int, BotPlayer]) -> None:
        """
        Initialize bot controller with seat-to-bot mapping.
        """
        self._bots = bots

    def _get_bot(self, seat: int) -> BotPlayer | None:
        """
        Get the bot instance for a given seat.
        """
        return self._bots.get(seat)

    def is_bot(self, seat: int) -> bool:
        """
        Check if a seat is occupied by a bot.
        """
        return seat in self._bots

    def add_bot(self, seat: int, bot: BotPlayer) -> None:
        """
        Register a bot at a seat (replacing a disconnected human).
        """
        self._bots[seat] = bot

    @property
    def bot_seats(self) -> set[int]:
        """
        Return the set of seats occupied by bots.
        """
        return set(self._bots.keys())

    def get_turn_action(
        self,
        seat: int,
        round_state: MahjongRoundState,
    ) -> tuple[GameAction, dict[str, Any]] | None:
        """
        Get the bot's turn action as (action, data).

        Returns None if seat is not a bot.
        """
        bot = self._get_bot(seat)
        if bot is None:
            return None

        player = round_state.players[seat]
        action = get_bot_action(bot, player, round_state)

        # map bot action to GameAction + data dict for dispatch
        if action.action == PlayerAction.TSUMO:
            return GameAction.DECLARE_TSUMO, {}

        if action.action == PlayerAction.RIICHI:
            return GameAction.DECLARE_RIICHI, {"tile_id": action.tile_id}

        if action.action == PlayerAction.DISCARD:
            return GameAction.DISCARD, {"tile_id": action.tile_id}

        return None

    def get_call_response(  # noqa: PLR0911
        self,
        seat: int,
        round_state: MahjongRoundState,
        call_type: CallType,
        tile_id: int,
        caller_info: int | MeldCaller,
    ) -> tuple[GameAction, dict[str, Any]] | None:
        """
        Get the bot's call response as (action, data).

        Returns None if the bot declines (passes).
        """
        bot = self._get_bot(seat)
        if bot is None:
            return None

        player = round_state.players[seat]

        # ron/chankan opportunities
        if call_type in (CallType.RON, CallType.CHANKAN):
            if should_call_ron(bot, player, tile_id, round_state):
                return GameAction.CALL_RON, {}
            return None

        # unified discard prompt -- dispatch based on caller type
        if call_type == CallType.DISCARD:
            if isinstance(caller_info, int):
                # ron caller
                if should_call_ron(bot, player, tile_id, round_state):
                    return GameAction.CALL_RON, {}
                return None
            if isinstance(caller_info, MeldCaller):
                return _get_bot_meld_response(bot, player, caller_info, tile_id, round_state)
            return None

        # meld opportunities
        if call_type == CallType.MELD and isinstance(caller_info, MeldCaller):
            return _get_bot_meld_response(bot, player, caller_info, tile_id, round_state)

        return None


def _get_bot_meld_response(
    bot: BotPlayer,
    player: MahjongPlayer,
    caller_info: MeldCaller,
    tile_id: int,
    round_state: MahjongRoundState,
) -> tuple[GameAction, dict[str, Any]] | None:
    """
    Check bot's meld response.

    Returns (action, data) or None if bot declines.
    """
    meld_call_type = caller_info.call_type

    if meld_call_type == MeldCallType.PON and should_call_pon(bot, player, tile_id, round_state):
        return GameAction.CALL_PON, {"tile_id": tile_id}

    if meld_call_type == MeldCallType.CHI and should_call_chi(
        bot, player, tile_id, caller_info.options, round_state
    ):
        if caller_info.options:
            return GameAction.CALL_CHI, {"tile_id": tile_id, "sequence_tiles": caller_info.options[0]}
        return None

    if meld_call_type == MeldCallType.OPEN_KAN and should_call_kan(
        bot, player, KanType.OPEN, tile_id, round_state
    ):
        return GameAction.CALL_KAN, {"tile_id": tile_id, "kan_type": KanType.OPEN}

    return None
