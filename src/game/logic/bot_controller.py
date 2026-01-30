"""
Bot controller for automated bot turn processing.

Handles bot turn automation and call responses independently from the game service.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from game.logic.abortive import check_four_riichi, process_abortive_draw
from game.logic.bot import (
    BotPlayer,
    get_bot_action,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_ron,
)
from game.logic.enums import AbortiveDrawType, CallType, KanType, MeldCallType, PlayerAction
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
from game.logic.types import BotAction, MeldCaller, RoundResult
from game.messaging.events import (
    CallPromptEvent,
    EventType,
    RiichiDeclaredEvent,
    RoundEndEvent,
    ServiceEvent,
    convert_events,
    extract_round_result,
)

# type alias for round end callback
RoundEndCallback = Callable[[RoundResult | None], Awaitable[list[ServiceEvent]]]


@dataclass
class BotCallEvaluation:
    """Result of evaluating a bot's call response."""

    call_type: CallType  # CallType.RON or CallType.MELD
    caller_seat: int
    meld_type: MeldCallType | None = None
    sequence_tiles: tuple[int, int] | None = None


def _get_bot_meld_response(
    bot: BotPlayer,
    player: MahjongPlayer,
    call_info: tuple[MeldCallType | None, list[tuple[int, int]] | None],
    tile_id: int,
    round_state: MahjongRoundState,
) -> tuple[MeldCallType, tuple[int, int] | None] | None:
    """
    Check bot's meld response.

    Returns (meld_type, sequence_tiles) or None. sequence_tiles is only set for chi.
    """
    meld_call_type, caller_options = call_info
    if meld_call_type == MeldCallType.PON and should_call_pon(bot, player, tile_id, round_state):
        return (MeldCallType.PON, None)
    if meld_call_type == MeldCallType.CHI and should_call_chi(
        bot, player, tile_id, caller_options or [], round_state
    ):
        # use first available chi option
        if caller_options and caller_options[0]:
            return (MeldCallType.CHI, tuple(caller_options[0]))
        return None
    if meld_call_type == MeldCallType.OPEN_KAN and should_call_kan(
        bot, player, KanType.OPEN, tile_id, round_state
    ):
        return (MeldCallType.OPEN_KAN, None)
    return None


class BotController:
    """
    Controller for automated bot turn processing.

    Manages bot decision-making during game turns and handles responses to call prompts.
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

    def has_human_caller(self, round_state: MahjongRoundState, events: list[ServiceEvent]) -> bool:
        """
        Check if any human player can respond to a call prompt in the events.

        Returns True if at least one human player has a pending call opportunity.
        """
        for event in events:
            if not isinstance(event.data, CallPromptEvent):
                continue
            for caller_info in event.data.callers:
                caller_seat = caller_info if isinstance(caller_info, int) else caller_info.seat
                if caller_seat is not None and not round_state.players[caller_seat].is_bot:
                    return True
        return False

    async def process_bot_turns(
        self,
        game_state: MahjongGameState,
        on_round_end: RoundEndCallback | None = None,
    ) -> list[ServiceEvent]:
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
        events: list[ServiceEvent] = []

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
            has_call_prompt = any(e.event == EventType.CALL_PROMPT for e in turn_events)
            if has_call_prompt and self.has_human_caller(round_state, turn_events):
                break

        return events

    async def _process_single_bot_turn(
        self,
        game_state: MahjongGameState,
        bot: BotPlayer,
        current_seat: int,
        on_round_end: RoundEndCallback | None = None,
    ) -> list[ServiceEvent]:
        """Process a single bot's turn and return events."""
        round_state = game_state.round_state
        current_player = round_state.players[current_seat]

        action = get_bot_action(bot, current_player, round_state)
        action_type = action.action
        events: list[ServiceEvent] = []

        if action_type == PlayerAction.TSUMO:
            tsumo_events = process_tsumo_call(round_state, game_state, current_seat)
            events.extend(convert_events(tsumo_events))
            return events

        if action_type in (PlayerAction.RIICHI, PlayerAction.DISCARD):
            discard_events = self._process_bot_discard(action, round_state, game_state)
            events.extend(discard_events)

        if round_state.phase == RoundPhase.FINISHED:
            return events

        # handle call prompts from discard
        has_call_prompt = any(e.event == EventType.CALL_PROMPT for e in events)
        if has_call_prompt:
            # check if any human player can respond to the call prompt
            if self.has_human_caller(round_state, events):
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

    def _process_bot_discard(
        self,
        action: BotAction,
        round_state: MahjongRoundState,
        game_state: MahjongGameState,
    ) -> list[ServiceEvent]:
        """Process a bot's discard or riichi action."""
        tile_id = action.tile_id
        if tile_id is None:
            raise ValueError("tile_id required for discard action")
        is_riichi = action.action == PlayerAction.RIICHI
        discard_events = process_discard_phase(round_state, game_state, tile_id, is_riichi=is_riichi)
        return convert_events(discard_events)

    async def process_call_responses(
        self,
        game_state: MahjongGameState,
        events: list[ServiceEvent],
        on_round_end: RoundEndCallback | None = None,
    ) -> list[ServiceEvent]:
        """
        Process bot responses to call prompts (ron, pon, chi, kan).

        Returns events generated from bot calls.
        """
        call_prompts = [e for e in events if e.event == EventType.CALL_PROMPT]
        result_events: list[ServiceEvent] = []

        for prompt in call_prompts:
            prompt_events = await self._process_single_prompt(game_state, prompt, on_round_end)
            result_events.extend(prompt_events)
            if prompt_events:
                return result_events

        return result_events

    async def _process_single_prompt(
        self,
        game_state: MahjongGameState,
        prompt: ServiceEvent,
        on_round_end: RoundEndCallback | None = None,
    ) -> list[ServiceEvent]:
        """Process a single call prompt and return any resulting events."""
        if not isinstance(prompt.data, CallPromptEvent):
            return []

        round_state = game_state.round_state
        call_prompt = prompt.data
        call_type = call_prompt.call_type
        tile_id = call_prompt.tile_id
        from_seat = call_prompt.from_seat
        callers = call_prompt.callers

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
        result_events: list[ServiceEvent] = []

        # check if the discarder had a pending riichi declaration
        discarder = round_state.players[from_seat]
        if discarder.discards and discarder.discards[-1].is_riichi_discard:
            declare_riichi(discarder, game_state)
            result_events.extend(convert_events([RiichiDeclaredEvent(seat=from_seat, target="all")]))

            # check for four riichi abortive draw
            if check_four_riichi(round_state):
                abortive_result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_RIICHI)
                round_state.phase = RoundPhase.FINISHED
                result_events.extend(convert_events([RoundEndEvent(result=abortive_result, target="all")]))
                return result_events

        advance_turn(round_state)
        return result_events

    def _evaluate_bot_calls(
        self,
        round_state: MahjongRoundState,
        callers: list[int] | list[MeldCaller],
        call_type: CallType,
        tile_id: int,
    ) -> tuple[list[int], int | None, MeldCallType | None, tuple[int, int] | None]:
        """
        Evaluate which bots want to make calls.

        Returns (ron_callers, meld_caller, meld_type, sequence_tiles).
        """
        ron_callers: list[int] = []
        meld_caller: int | None = None
        meld_type: MeldCallType | None = None
        sequence_tiles: tuple[int, int] | None = None

        for caller_info in callers:
            result = self._evaluate_single_caller(round_state, caller_info, call_type, tile_id)
            if result is None:
                continue
            if result.call_type == CallType.RON:
                ron_callers.append(result.caller_seat)
            elif result.call_type == CallType.MELD and result.meld_type:
                meld_caller = result.caller_seat
                meld_type = result.meld_type
                sequence_tiles = result.sequence_tiles

        return ron_callers, meld_caller, meld_type, sequence_tiles

    def _evaluate_single_caller(
        self,
        round_state: MahjongRoundState,
        caller_info: int | MeldCaller,
        call_type: CallType,
        tile_id: int,
    ) -> BotCallEvaluation | None:
        """Evaluate a single caller's response."""
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
        if call_type in (CallType.RON, CallType.CHANKAN) and should_call_ron(
            bot, player, tile_id, round_state
        ):
            return BotCallEvaluation(call_type=CallType.RON, caller_seat=caller_seat)

        if call_type == CallType.MELD and isinstance(caller_info, MeldCaller):
            meld_result = _get_bot_meld_response(
                bot, player, (caller_info.call_type, caller_options), tile_id, round_state
            )
            if meld_result:
                result_meld_type, seq_tiles = meld_result
                return BotCallEvaluation(
                    call_type=CallType.MELD,
                    caller_seat=caller_seat,
                    meld_type=result_meld_type,
                    sequence_tiles=seq_tiles,
                )

        return None

    def _parse_caller_info(
        self, caller_info: int | MeldCaller
    ) -> tuple[int | None, list[tuple[int, int]] | None]:
        """Parse caller info which can be int (seat) or MeldCaller model."""
        if isinstance(caller_info, int):
            return caller_info, None
        return caller_info.seat, caller_info.options
