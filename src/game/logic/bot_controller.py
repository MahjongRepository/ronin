"""
Bot controller for automated bot turn processing.

Handles bot turn automation and call responses independently from the game service.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from game.logic.abortive import AbortiveDrawType, check_four_riichi, process_abortive_draw
from game.logic.bot import (
    BotPlayer,
    get_bot_action,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_ron,
)
from game.logic.riichi import declare_riichi
from game.logic.round import advance_turn
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState, RoundPhase
from game.logic.turn import (
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.messaging.events import (
    RiichiDeclaredEvent,
    RoundEndEvent,
    convert_events,
    extract_round_result,
)

# type alias for round end callback
RoundEndCallback = Callable[[dict | None], Awaitable[list[dict[str, Any]]]]


@dataclass
class BotCallEvaluation:
    """Result of evaluating a bot's call response."""

    call_type: str  # "ron" or "meld"
    caller_seat: int
    meld_type: str | None = None
    sequence_tiles: tuple[int, int] | None = None


def _get_bot_meld_response(
    bot: BotPlayer,
    player: MahjongPlayer,
    call_info: tuple[str | None, list | None],
    tile_id: int,
    round_state: MahjongRoundState,
) -> tuple[str, tuple[int, int] | None] | None:
    """
    Check bot's meld response.

    Returns (meld_type, sequence_tiles) or None. sequence_tiles is only set for chi.
    """
    meld_call_type, caller_options = call_info
    if meld_call_type == "pon" and should_call_pon(bot, player, tile_id, round_state):
        return ("pon", None)
    if meld_call_type == "chi" and should_call_chi(bot, player, tile_id, caller_options or [], round_state):
        # use first available chi option
        if caller_options:
            sequence_tiles = tuple(caller_options[0]) if caller_options[0] else None
            return ("chi", sequence_tiles)
        return None
    if meld_call_type == "open_kan" and should_call_kan(bot, player, "open", tile_id, round_state):
        return ("open_kan", None)
    return None


class BotController:
    """
    Controller for automated bot turn processing.

    Manages bot decision-making during game turns and handles responses to call prompts.
    Bots are indexed by seat-1 since seat 0 is reserved for the human player.
    """

    def __init__(self, bots: list[BotPlayer]) -> None:
        """
        Initialize bot controller with a list of bot players.

        Args:
            bots: List of BotPlayer instances (typically 3 for seats 1-3)

        """
        self._bots = bots

    def _get_bot(self, seat: int) -> BotPlayer | None:
        """
        Get the bot instance for a given seat.

        Returns None if seat is invalid or not a bot seat.
        """
        bot_index = seat - 1
        if bot_index < 0 or bot_index >= len(self._bots):
            return None
        return self._bots[bot_index]

    def has_human_caller(self, round_state: MahjongRoundState, events: list[dict[str, Any]]) -> bool:
        """
        Check if any human player can respond to a call prompt in the events.

        Returns True if at least one human player has a pending call opportunity.
        """
        for event in events:
            if event.get("event") != "call_prompt":
                continue
            callers = event.get("data", {}).get("callers", [])
            for caller_info in callers:
                caller_seat = caller_info if isinstance(caller_info, int) else caller_info.get("seat")
                if caller_seat is not None:
                    player = round_state.players[caller_seat]
                    if not player.is_bot:
                        return True
        return False

    async def process_bot_turns(
        self,
        game_state: MahjongGameState,
        on_round_end: RoundEndCallback | None = None,
    ) -> list[dict[str, Any]]:
        """
        Process bot turns until it's a human player's turn.

        Continues processing until:
        - A human player's turn is reached
        - The round ends
        - A call prompt requires human response

        Args:
            game_state: The current game state
            on_round_end: Optional async callback for round end handling

        Returns:
            List of events generated during bot turns

        """
        round_state = game_state.round_state
        events: list[dict[str, Any]] = []

        for _ in range(100):  # safety limit
            if round_state.phase == RoundPhase.FINISHED:
                break

            current_seat = round_state.current_player_seat
            current_player = round_state.players[current_seat]

            if not current_player.is_bot:
                break

            bot = self._get_bot(current_seat)
            if bot is None:
                break

            turn_events = await self._process_single_bot_turn(game_state, bot, current_seat, on_round_end)
            events.extend(turn_events)

            if round_state.phase == RoundPhase.FINISHED:
                break

            # check if we're waiting for human input on a call prompt
            has_call_prompt = any(e.get("event") == "call_prompt" for e in turn_events)
            if has_call_prompt and self.has_human_caller(round_state, turn_events):
                break

        return events

    async def _process_single_bot_turn(
        self,
        game_state: MahjongGameState,
        bot: BotPlayer,
        current_seat: int,
        on_round_end: RoundEndCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Process a single bot's turn and return events."""
        round_state = game_state.round_state
        current_player = round_state.players[current_seat]

        action = get_bot_action(bot, current_player, round_state)
        action_type = action.get("action")
        events: list[dict[str, Any]] = []

        if action_type == "tsumo":
            tsumo_events = process_tsumo_call(round_state, game_state, current_seat)
            events.extend(convert_events(tsumo_events))
            return events

        if action_type in ("riichi", "discard"):
            tile_id = action.get("tile_id")
            is_riichi = action_type == "riichi"
            discard_events = process_discard_phase(round_state, game_state, tile_id, is_riichi=is_riichi)
            events.extend(convert_events(discard_events))

        if round_state.phase == RoundPhase.FINISHED:
            return events

        # handle call prompts from discard
        has_call_prompt = any(e.get("event") == "call_prompt" for e in events)
        if has_call_prompt:
            # check if any human player can respond to the call prompt
            human_can_call = self.has_human_caller(round_state, events)
            if human_can_call:
                # wait for human response - don't advance the game
                return events

            bot_responses = await self.process_call_responses(game_state, events, on_round_end)
            events.extend(bot_responses)
            if round_state.phase == RoundPhase.FINISHED:
                return events

        # draw for next player
        if round_state.phase == RoundPhase.PLAYING:
            draw_events = process_draw_phase(round_state, game_state)
            events.extend(convert_events(draw_events))

            # check if draw phase caused round to end (exhaustive draw)
            if round_state.phase == RoundPhase.FINISHED:
                result = extract_round_result(events)
                if on_round_end:
                    end_events = await on_round_end(result)
                    events.extend(end_events)

        return events

    async def process_call_responses(
        self,
        game_state: MahjongGameState,
        events: list[dict[str, Any]],
        on_round_end: RoundEndCallback | None = None,
    ) -> list[dict[str, Any]]:
        """
        Process bot responses to call prompts (ron, pon, chi, kan).

        Returns events generated from bot calls.
        """
        call_prompts = [e for e in events if e.get("event") == "call_prompt"]
        result_events: list[dict[str, Any]] = []

        for prompt in call_prompts:
            prompt_events = await self._process_single_prompt(game_state, prompt, on_round_end)
            result_events.extend(prompt_events)
            if prompt_events:
                return result_events

        return result_events

    async def _process_single_prompt(
        self,
        game_state: MahjongGameState,
        prompt: dict[str, Any],
        on_round_end: RoundEndCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Process a single call prompt and return any resulting events."""
        round_state = game_state.round_state

        prompt_data = prompt.get("data", {})
        call_type = prompt_data.get("call_type")
        tile_id = prompt_data.get("tile_id")
        from_seat = prompt_data.get("from_seat")
        callers = prompt_data.get("callers", [])

        ron_callers, meld_caller, meld_type, sequence_tiles = self._evaluate_bot_calls(
            round_state, callers, call_type, tile_id
        )

        if ron_callers:
            ron_events = process_ron_call(round_state, game_state, ron_callers, tile_id, from_seat)
            return convert_events(ron_events)

        if meld_caller is not None and meld_type is not None:
            meld_events = process_meld_call(
                round_state, game_state, meld_caller, meld_type, tile_id, sequence_tiles=sequence_tiles
            )
            result = convert_events(meld_events)
            bot_turn_events = await self.process_bot_turns(game_state, on_round_end)
            result.extend(bot_turn_events)
            return result

        # no bot wants to call - finalize pending riichi if any, then advance turn
        result_events: list[dict[str, Any]] = []

        # check if the discarder had a pending riichi declaration
        if from_seat is not None:
            discarder = round_state.players[from_seat]
            if discarder.discards and discarder.discards[-1].is_riichi_discard:
                # finalize the riichi declaration
                declare_riichi(discarder, game_state)
                result_events.extend(convert_events([RiichiDeclaredEvent(seat=from_seat, target="all")]))

                # check for four riichi abortive draw
                if check_four_riichi(round_state):
                    result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_RIICHI)
                    round_state.phase = RoundPhase.FINISHED
                    result_events.extend(convert_events([RoundEndEvent(result=result, target="all")]))
                    return result_events

        advance_turn(round_state)
        return result_events

    def _evaluate_bot_calls(
        self,
        round_state: MahjongRoundState,
        callers: list,
        call_type: str,
        tile_id: int,
    ) -> tuple[list[int], int | None, str | None, tuple[int, int] | None]:
        """
        Evaluate which bots want to make calls.

        Returns (ron_callers, meld_caller, meld_type, sequence_tiles).
        """
        ron_callers: list[int] = []
        meld_caller: int | None = None
        meld_type: str | None = None
        sequence_tiles: tuple[int, int] | None = None

        for caller_info in callers:
            result = self._evaluate_single_caller(round_state, caller_info, call_type, tile_id)
            if result is None:
                continue
            if result.call_type == "ron":
                ron_callers.append(result.caller_seat)
            elif result.call_type == "meld" and result.meld_type:
                meld_caller = result.caller_seat
                meld_type = result.meld_type
                sequence_tiles = result.sequence_tiles

        return ron_callers, meld_caller, meld_type, sequence_tiles

    def _evaluate_single_caller(
        self,
        round_state: MahjongRoundState,
        caller_info: int | dict,
        call_type: str,
        tile_id: int,
    ) -> BotCallEvaluation | None:
        """
        Evaluate a single caller's response.
        """
        caller_seat, caller_options = self._parse_caller_info(caller_info)
        if caller_seat is None:
            return None

        player = round_state.players[caller_seat]
        if not player.is_bot:
            return None

        bot = self._get_bot(caller_seat)
        if bot is None:
            return None

        # chankan is a ron opportunity on the added kan tile
        if call_type in ("ron", "chankan") and should_call_ron(bot, player, tile_id, round_state):
            return BotCallEvaluation(call_type="ron", caller_seat=caller_seat)

        if call_type == "meld":
            meld_call_type = caller_info.get("call_type") if isinstance(caller_info, dict) else None
            meld_result = _get_bot_meld_response(
                bot, player, (meld_call_type, caller_options), tile_id, round_state
            )
            if meld_result:
                result_meld_type, seq_tiles = meld_result
                return BotCallEvaluation(
                    call_type="meld",
                    caller_seat=caller_seat,
                    meld_type=result_meld_type,
                    sequence_tiles=seq_tiles,
                )

        return None

    def _parse_caller_info(self, caller_info: int | dict) -> tuple[int | None, list | None]:
        """Parse caller info which can be int (seat) or dict with seat/options."""
        if isinstance(caller_info, int):
            return caller_info, None
        return caller_info.get("seat"), caller_info.get("options")
