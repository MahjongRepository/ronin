"""
MahjongGameService implementation for the Mahjong game.

Orchestrates game logic, bot turns, and event generation for the session manager.
"""

from functools import partial
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

from game.logic.action_handlers import (
    ActionResult,
    complete_added_kan_after_chankan_decline,
    handle_chi,
    handle_discard,
    handle_kan,
    handle_kyuushu,
    handle_pass,
    handle_pon,
    handle_riichi,
    handle_ron,
    handle_tsumo,
)
from game.logic.bot import BotPlayer, BotStrategy
from game.logic.bot_controller import BotController
from game.logic.enums import BotType, CallType, GameAction, TimeoutType
from game.logic.game import check_game_end, finalize_game, init_game, process_round_end
from game.logic.matchmaker import fill_seats
from game.logic.round import init_round
from game.logic.service import GameService
from game.logic.state import MahjongGameState, RoundPhase, get_player_view
from game.logic.turn import process_draw_phase
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    KanActionData,
    PonActionData,
    RiichiActionData,
    RonActionData,
)
from game.messaging.events import (
    CallPromptEvent,
    ErrorEvent,
    EventType,
    GameEndedEvent,
    GameStartedEvent,
    RoundStartedEvent,
    ServiceEvent,
    convert_events,
    extract_round_result,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from game.logic.types import RoundResult


_BOT_TYPE_TO_STRATEGY: dict[BotType, BotStrategy] = {
    BotType.TSUMOGIRI: BotStrategy.TSUMOGIRI,
}


class MahjongGameService(GameService):
    """
    Game service for Mahjong implementing the GameService interface.

    Maintains game states for multiple concurrent games and handles all
    player actions including bot turn automation.
    """

    def __init__(self) -> None:
        self._games: dict[str, MahjongGameState] = {}
        self._bot_controllers: dict[str, BotController] = {}

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
    ) -> list[ServiceEvent]:
        """
        Start a new mahjong game with the given players.

        Uses matchmaker to assign seats randomly and fill with bots.
        Returns initial state events for each player.
        """
        seat_configs = fill_seats(player_names)
        game_state = init_game(seat_configs)
        self._games[game_id] = game_state

        bots: dict[int, BotPlayer] = {}
        for seat, config in enumerate(seat_configs):
            if config.is_bot:
                strategy = _BOT_TYPE_TO_STRATEGY.get(config.bot_type) if config.bot_type else None
                bots[seat] = BotPlayer(strategy=strategy or BotStrategy.TSUMOGIRI)

        self._bot_controllers[game_id] = BotController(bots)

        events: list[ServiceEvent] = []
        events.extend(self._create_game_started_events(game_state))

        draw_events = process_draw_phase(game_state.round_state, game_state)
        events.extend(convert_events(draw_events))

        # process bot turns if dealer is a bot
        dealer_seat = game_state.round_state.dealer_seat
        if game_state.round_state.players[dealer_seat].is_bot:
            bot_events = await self._process_bot_turns(game_id)
            events.extend(bot_events)

        return events

    def _create_game_started_events(self, game_state: MahjongGameState) -> list[ServiceEvent]:
        """Create game_started events for all players."""
        return [
            ServiceEvent(
                event=EventType.GAME_STARTED,
                data=GameStartedEvent(
                    view=get_player_view(game_state, seat),
                    target=f"seat_{seat}",
                ),
                target=f"seat_{seat}",
            )
            for seat in range(4)
        ]

    async def handle_action(
        self,
        game_id: str,
        player_name: str,
        action: str,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Handle a game action from a player.

        Processes the action and triggers bot turns as needed.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return self._create_error_event("game_error", "game not found")

        seat = self._find_player_seat(game_state, player_name)
        if seat is None:
            return self._create_error_event("game_error", "player not in game")

        return await self._dispatch_action(game_id, seat, action, data)

    async def _dispatch_action(
        self, game_id: str, seat: int, action: str, data: dict[str, Any]
    ) -> list[ServiceEvent]:
        """Dispatch action to appropriate handler."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # actions without data parameters
        no_data_handlers = {
            GameAction.DECLARE_TSUMO: lambda: handle_tsumo(round_state, game_state, seat),
            GameAction.CALL_KYUUSHU: lambda: handle_kyuushu(round_state, game_state, seat),
            GameAction.PASS: lambda: handle_pass(round_state, game_state, seat),
        }

        handler = no_data_handlers.get(action)
        if handler is not None:
            return await self._process_action_result(game_id, handler())

        # actions with data parameters
        try:
            result = self._execute_data_action(game_state, seat, action, data)
        except ValidationError as e:
            return self._create_error_event(
                "validation_error", f"invalid action data: {e}", target=f"seat_{seat}"
            )

        if result is None:
            return self._create_error_event(
                "unknown_action", f"unknown action: {action}", target=f"seat_{seat}"
            )

        return await self._process_action_result(game_id, result)

    def _execute_data_action(  # noqa: PLR0911
        self, game_state: MahjongGameState, seat: int, action: str, data: dict[str, Any]
    ) -> ActionResult | None:
        """Execute data-requiring actions and return the result."""
        round_state = game_state.round_state
        if action == GameAction.DISCARD:
            return handle_discard(round_state, game_state, seat, DiscardActionData(**data))
        if action == GameAction.DECLARE_RIICHI:
            return handle_riichi(round_state, game_state, seat, RiichiActionData(**data))
        if action == GameAction.CALL_RON:
            return handle_ron(round_state, game_state, seat, RonActionData(**data))
        if action == GameAction.CALL_PON:
            return handle_pon(round_state, game_state, seat, PonActionData(**data))
        if action == GameAction.CALL_CHI:
            return handle_chi(round_state, game_state, seat, ChiActionData(**data))
        if action == GameAction.CALL_KAN:
            return handle_kan(round_state, game_state, seat, KanActionData(**data))
        return None

    async def _process_action_result(self, game_id: str, result: ActionResult) -> list[ServiceEvent]:
        """Process action result and handle post-action logic."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        events = convert_events(result.events)

        # check if round ended
        round_end_events = await self._check_and_handle_round_end(game_id, events)
        if round_end_events is not None:
            return round_end_events

        if result.needs_post_discard:
            return await self._process_post_discard(game_id, events)

        # check for chankan prompt
        chankan_prompt = self._find_chankan_prompt(events)
        if chankan_prompt:
            return await self._handle_chankan_prompt(game_id, events, chankan_prompt)

        # process bot turns if needed
        if round_state.phase == RoundPhase.PLAYING:
            current_player = round_state.players[round_state.current_player_seat]
            if current_player.is_bot:
                bot_events = await self._process_bot_turns(game_id)
                events.extend(bot_events)

        return events

    def _find_chankan_prompt(self, events: list[ServiceEvent]) -> ServiceEvent | None:
        """Find a chankan call prompt in events."""
        return next(
            (
                e
                for e in events
                if isinstance(e.data, CallPromptEvent) and e.data.call_type == CallType.CHANKAN
            ),
            None,
        )

    async def _handle_chankan_prompt(
        self, game_id: str, events: list[ServiceEvent], chankan_prompt: ServiceEvent
    ) -> list[ServiceEvent]:
        """Handle chankan prompt: wait for human or process bot response."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        bot_controller = self._bot_controllers[game_id]

        if bot_controller.has_human_caller(round_state, events):
            return events

        bot_responses = await bot_controller.process_call_responses(
            game_state, events, partial(self._round_end_callback, game_id)
        )
        events.extend(bot_responses)

        # check if round ended after bot responses
        round_end_events = await self._check_and_handle_round_end(game_id, events)
        if round_end_events is not None:
            return round_end_events

        # chankan was declined, complete the added kan
        # _find_chankan_prompt guarantees data is CallPromptEvent
        call_prompt_data = cast("CallPromptEvent", chankan_prompt.data)
        kan_events = complete_added_kan_after_chankan_decline(
            round_state, game_state, call_prompt_data.from_seat, call_prompt_data.tile_id
        )
        events.extend(convert_events(kan_events))

        # check if four-kans abortive draw occurred
        round_end_events = await self._check_and_handle_round_end(game_id, events)
        if round_end_events is not None:
            return round_end_events

        return events

    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """
        Get the seat number for a player by name.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return None
        return self._find_player_seat(game_state, player_name)

    async def handle_timeout(
        self,
        game_id: str,
        player_name: str,
        timeout_type: TimeoutType,
    ) -> list[ServiceEvent]:
        """
        Handle a player timeout by performing the default action.

        For TURN timeout: tsumogiri (discard last drawn tile).
        For MELD timeout: pass on the call opportunity.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        seat = self._find_player_seat(game_state, player_name)
        if seat is None:
            return []

        if timeout_type == TimeoutType.TURN:
            # tsumogiri: discard the last tile in hand (most recently drawn)
            player = game_state.round_state.players[seat]
            if game_state.round_state.current_player_seat != seat or not player.tiles:
                return []
            tile_id = player.tiles[-1]
            return await self._dispatch_action(game_id, seat, GameAction.DISCARD, {"tile_id": tile_id})

        if timeout_type == TimeoutType.MELD:
            return await self._dispatch_action(game_id, seat, GameAction.PASS, {})

        raise ValueError(f"Unknown timeout type: {timeout_type}")

    def _find_player_seat(self, game_state: MahjongGameState, player_name: str) -> int | None:
        """Find the seat number for a human player by name."""
        for player in game_state.round_state.players:
            if player.name == player_name and not player.is_bot:
                return player.seat
        return None

    def _create_error_event(self, code: str, message: str, target: str = "all") -> list[ServiceEvent]:
        """Create an error event wrapped in a ServiceEvent."""
        return [
            ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(code=code, message=message, target=target),
                target=target,
            )
        ]

    async def _check_and_handle_round_end(
        self, game_id: str, events: list[ServiceEvent]
    ) -> list[ServiceEvent] | None:
        """
        Check if round has ended and handle accordingly.

        Returns the extended events list if round ended, None otherwise.
        """
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.phase != RoundPhase.FINISHED:
            return None

        result = extract_round_result(events)
        events.extend(await self._handle_round_end(game_id, result))
        return events

    async def _process_post_discard(self, game_id: str, events: list[ServiceEvent]) -> list[ServiceEvent]:
        """Process events after a discard (check round end, call prompts, bot turns)."""
        game_state = self._games[game_id]
        round_state = game_state.round_state
        bot_controller = self._bot_controllers[game_id]

        # check if round ended immediately
        round_end_events = await self._check_and_handle_round_end(game_id, events)
        if round_end_events is not None:
            return round_end_events

        # handle call prompts from discard
        has_call_prompt = any(e.event == EventType.CALL_PROMPT for e in events)
        if has_call_prompt:
            if bot_controller.has_human_caller(round_state, events):
                return events

            bot_responses = await bot_controller.process_call_responses(
                game_state, events, partial(self._round_end_callback, game_id)
            )
            events.extend(bot_responses)

            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events

        # draw for next player
        if round_state.phase == RoundPhase.PLAYING:
            draw_events = process_draw_phase(round_state, game_state)
            events.extend(convert_events(draw_events))

            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events

        # process bot turns if next player is a bot
        if round_state.phase == RoundPhase.PLAYING:
            current_player = round_state.players[round_state.current_player_seat]
            if current_player.is_bot:
                bot_events = await self._process_bot_turns(game_id)
                events.extend(bot_events)

        return events

    async def _handle_round_end(
        self, game_id: str, round_result: RoundResult | None = None
    ) -> list[ServiceEvent]:
        """Handle the end of a round and start next round or end game."""
        game_state = self._games[game_id]

        if round_result is None:
            return self._create_error_event(
                "missing_round_result",
                "round finished but no round result found",
            )
        process_round_end(game_state, round_result)

        if check_game_end(game_state):
            game_result = finalize_game(game_state)
            self._cleanup_game(game_id)
            return [
                ServiceEvent(
                    event=EventType.GAME_END,
                    data=GameEndedEvent(result=game_result, target="all"),
                    target="all",
                )
            ]

        return await self._start_next_round(game_id)

    def _cleanup_game(self, game_id: str) -> None:
        """Clean up game state after game ends."""
        self._games.pop(game_id, None)
        self._bot_controllers.pop(game_id, None)

    async def _start_next_round(self, game_id: str) -> list[ServiceEvent]:
        """Start the next round and return events."""
        game_state = self._games[game_id]
        init_round(game_state)

        events: list[ServiceEvent] = [
            ServiceEvent(
                event=EventType.ROUND_STARTED,
                data=RoundStartedEvent(
                    view=get_player_view(game_state, seat),
                    target=f"seat_{seat}",
                ),
                target=f"seat_{seat}",
            )
            for seat in range(4)
        ]

        round_state = game_state.round_state
        draw_events = process_draw_phase(round_state, game_state)
        events.extend(convert_events(draw_events))

        dealer_seat = round_state.dealer_seat
        if round_state.players[dealer_seat].is_bot:
            bot_events = await self._process_bot_turns(game_id)
            events.extend(bot_events)

        return events

    def _round_end_callback(self, game_id: str, result: RoundResult | None) -> Awaitable[list[ServiceEvent]]:
        """Handle round end and return events."""
        return self._handle_round_end(game_id, result)

    async def _process_bot_turns(self, game_id: str) -> list[ServiceEvent]:
        """Process bot turns using BotController."""
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        bot_controller = self._bot_controllers.get(game_id)
        if bot_controller is None:
            return []

        return await bot_controller.process_bot_turns(game_state, partial(self._round_end_callback, game_id))
