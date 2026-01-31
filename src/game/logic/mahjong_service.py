"""
MahjongGameService implementation for the Mahjong game.

Orchestrates game logic, bot turns, and event generation for the session manager.
"""

import logging
from typing import Any

from pydantic import ValidationError

from game.logic.action_handlers import (
    ActionResult,
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
from game.logic.state import MahjongGameState, PendingCallPrompt, RoundPhase, get_player_view
from game.logic.turn import process_draw_phase
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    GamePlayerInfo,
    KanActionData,
    MeldCaller,
    PonActionData,
    RiichiActionData,
    RoundResult,
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

logger = logging.getLogger(__name__)

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
        logger.info(f"starting game {game_id} with players: {player_names}")
        seat_configs = fill_seats(player_names)
        game_state = init_game(seat_configs)
        self._games[game_id] = game_state

        bots: dict[int, BotPlayer] = {}
        for seat, config in enumerate(seat_configs):
            if config.bot_type is not None:
                strategy = _BOT_TYPE_TO_STRATEGY.get(config.bot_type, BotStrategy.TSUMOGIRI)
                bots[seat] = BotPlayer(strategy=strategy)

        bot_controller = BotController(bots)
        self._bot_controllers[game_id] = bot_controller

        events: list[ServiceEvent] = []
        events.append(self._create_game_started_event(game_state, bot_seats=bot_controller.bot_seats))
        events.extend(self._create_round_started_events(game_state, bot_seats=bot_controller.bot_seats))

        draw_events = process_draw_phase(game_state.round_state, game_state)
        events.extend(convert_events(draw_events))

        # process bot turns if dealer is a bot
        dealer_seat = game_state.round_state.dealer_seat
        if bot_controller.is_bot(dealer_seat):
            bot_events = await self._process_bot_followup(game_id)
            events.extend(bot_events)

        return events

    def _create_game_started_event(
        self, game_state: MahjongGameState, bot_seats: set[int] | None = None
    ) -> ServiceEvent:
        """Create a single game_started event broadcast to all players."""
        players = [
            GamePlayerInfo(
                seat=p.seat,
                name=p.name,
                is_bot=p.seat in (bot_seats or set()),
            )
            for p in game_state.round_state.players
        ]
        return ServiceEvent(
            event=EventType.GAME_STARTED,
            data=GameStartedEvent(players=players),
            target="all",
        )

    def _create_round_started_events(
        self, game_state: MahjongGameState, bot_seats: set[int] | None = None
    ) -> list[ServiceEvent]:
        """Create round_started events for all players."""
        return [
            ServiceEvent(
                event=EventType.ROUND_STARTED,
                data=RoundStartedEvent(
                    view=get_player_view(game_state, seat, bot_seats=bot_seats),
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
            logger.warning(f"game {game_id}: action from '{player_name}' but game not found")
            return self._create_error_event("game_error", "game not found")

        seat = self._find_player_seat(game_id, game_state, player_name)
        if seat is None:
            logger.warning(f"game {game_id}: action from '{player_name}' but player not in game")
            return self._create_error_event("game_error", "player not in game")

        logger.info(f"game {game_id}: player '{player_name}' (seat {seat}) action={action}")
        events = await self._dispatch_and_process(game_id, seat, action, data)

        # trigger bot followup if round is playing and no pending callers
        round_state = game_state.round_state
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            bot_events = await self._process_bot_followup(game_id)
            events.extend(bot_events)

        return events

    async def _dispatch_and_process(
        self, game_id: str, seat: int, action: str, data: dict[str, Any]
    ) -> list[ServiceEvent]:
        """
        Dispatch action to handler and process result.

        Does NOT trigger bot followup to avoid recursion.
        Bot followup is handled by the top-level caller.
        """
        game_state = self._games[game_id]

        # actions without data parameters
        no_data_handlers = {
            GameAction.DECLARE_TSUMO: lambda: handle_tsumo(game_state.round_state, game_state, seat),
            GameAction.CALL_RON: lambda: handle_ron(game_state.round_state, game_state, seat),
            GameAction.CALL_KYUUSHU: lambda: handle_kyuushu(game_state.round_state, game_state, seat),
            GameAction.PASS: lambda: handle_pass(game_state.round_state, game_state, seat),
        }

        handler = no_data_handlers.get(action)
        if handler is not None:
            result = handler()
            return await self._process_action_result_internal(game_id, result)

        # actions with data parameters
        try:
            result = self._execute_data_action(game_state, seat, action, data)
        except ValidationError as e:
            logger.warning(f"game {game_id}: validation error for seat {seat} action={action}: {e}")
            return self._create_error_event(
                "validation_error", f"invalid action data: {e}", target=f"seat_{seat}"
            )

        if result is None:
            logger.warning(f"game {game_id}: unknown action '{action}' from seat {seat}")
            return self._create_error_event(
                "unknown_action", f"unknown action: {action}", target=f"seat_{seat}"
            )

        return await self._process_action_result_internal(game_id, result)

    def _execute_data_action(
        self, game_state: MahjongGameState, seat: int, action: str, data: dict[str, Any]
    ) -> ActionResult | None:
        """Execute data-requiring actions and return the result."""
        round_state = game_state.round_state
        if action == GameAction.DISCARD:
            return handle_discard(round_state, game_state, seat, DiscardActionData(**data))
        if action == GameAction.DECLARE_RIICHI:
            return handle_riichi(round_state, game_state, seat, RiichiActionData(**data))
        if action == GameAction.CALL_PON:
            return handle_pon(round_state, game_state, seat, PonActionData(**data))
        if action == GameAction.CALL_CHI:
            return handle_chi(round_state, game_state, seat, ChiActionData(**data))
        if action == GameAction.CALL_KAN:
            return handle_kan(round_state, game_state, seat, KanActionData(**data))
        return None

    async def _process_action_result_internal(self, game_id: str, result: ActionResult) -> list[ServiceEvent]:
        """
        Process action result without triggering bot followup.

        Handles round end checking, post-discard processing, and chankan prompts.
        """
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
        self,
        game_id: str,
        events: list[ServiceEvent],
        chankan_prompt: ServiceEvent,  # noqa: ARG002
    ) -> list[ServiceEvent]:
        """Handle chankan prompt using the pending call prompt system."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.pending_call_prompt is None:
            return events

        # dispatch bot call responses through standard handlers
        self._dispatch_bot_call_responses(game_id, events)

        # if human callers still pending, wait
        if round_state.pending_call_prompt is not None:
            return events

        # resolved - check round end
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
        return self._find_player_seat(game_id, game_state, player_name)

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

        seat = self._find_player_seat(game_id, game_state, player_name)
        if seat is None:
            return []

        if timeout_type == TimeoutType.TURN:
            # tsumogiri: discard the last tile in hand (most recently drawn)
            player = game_state.round_state.players[seat]
            if game_state.round_state.current_player_seat != seat or not player.tiles:
                return []
            tile_id = player.tiles[-1]
            return await self.handle_action(game_id, player_name, GameAction.DISCARD, {"tile_id": tile_id})

        if timeout_type == TimeoutType.MELD:
            return await self.handle_action(game_id, player_name, GameAction.PASS, {})

        logger.error(f"game {game_id}: unknown timeout type '{timeout_type}' for player '{player_name}'")
        raise ValueError(f"Unknown timeout type: {timeout_type}")

    def _find_player_seat(self, game_id: str, game_state: MahjongGameState, player_name: str) -> int | None:
        """Find the seat number for a human player by name."""
        bot_controller = self._bot_controllers.get(game_id)
        for player in game_state.round_state.players:
            if player.name == player_name:
                if bot_controller and bot_controller.is_bot(player.seat):
                    continue
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
        """
        Process events after a discard.

        Uses the pending call prompt system: dispatches bot responses through handlers,
        waits for human callers, or advances turn if no callers.
        """
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # check if round ended immediately
        round_end_events = await self._check_and_handle_round_end(game_id, events)
        if round_end_events is not None:
            return round_end_events

        if round_state.pending_call_prompt is not None:
            # dispatch bot call responses through handlers
            self._dispatch_bot_call_responses(game_id, events)

            # if human callers still pending, wait
            if round_state.pending_call_prompt is not None:
                return events

            # prompt resolved - check round end
            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events
        elif round_state.phase == RoundPhase.PLAYING:
            # no callers - draw for next player (turn already advanced by process_discard_phase)
            draw_events = process_draw_phase(round_state, game_state)
            events.extend(convert_events(draw_events))

            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events

        return events

    def _dispatch_bot_call_responses(self, game_id: str, events: list[ServiceEvent]) -> None:
        """
        Dispatch bot responses to pending call prompt through standard handlers.

        Each bot's response goes through the same handle_pass/handle_pon/etc.
        functions as human responses. Resolution happens when all callers respond.
        """
        game_state = self._games[game_id]
        round_state = game_state.round_state
        bot_controller = self._bot_controllers[game_id]
        prompt = round_state.pending_call_prompt
        if prompt is None:
            return

        bot_seats = [s for s in list(prompt.pending_seats) if bot_controller.is_bot(s)]
        for seat in bot_seats:
            if round_state.pending_call_prompt is None:
                break  # already resolved

            caller_info = self._find_caller_info(prompt, seat)
            response = bot_controller.get_call_response(
                seat,
                round_state,
                prompt.call_type,
                prompt.tile_id,
                caller_info,
            )

            if response is not None:
                action, data = response
            else:
                action, data = GameAction.PASS, {}

            # call handler directly (same handler as human uses)
            result = self._call_handler(game_state, seat, action, data)
            events.extend(convert_events(result.events))

    def _call_handler(self, game_state: MahjongGameState, seat: int, action: str, data: dict) -> ActionResult:
        """Call the appropriate action handler directly."""
        round_state = game_state.round_state
        if action == GameAction.PASS:
            return handle_pass(round_state, game_state, seat)
        if action == GameAction.CALL_PON:
            return handle_pon(round_state, game_state, seat, PonActionData(**data))
        if action == GameAction.CALL_CHI:
            return handle_chi(round_state, game_state, seat, ChiActionData(**data))
        if action == GameAction.CALL_RON:
            return handle_ron(round_state, game_state, seat)
        if action == GameAction.CALL_KAN:
            return handle_kan(round_state, game_state, seat, KanActionData(**data))
        return ActionResult([])

    def _find_caller_info(self, prompt: PendingCallPrompt, seat: int) -> int | MeldCaller:
        """Find caller info for a seat from the prompt's callers list."""
        for caller in prompt.callers:
            caller_seat = caller if isinstance(caller, int) else caller.seat
            if caller_seat == seat:
                return caller
        return seat

    async def _handle_round_end(
        self, game_id: str, round_result: RoundResult | None = None
    ) -> list[ServiceEvent]:
        """Handle the end of a round and start next round or end game."""
        game_state = self._games[game_id]

        if round_result is None:
            logger.error(f"game {game_id}: round finished but no round result found in events")
            return self._create_error_event(
                "missing_round_result",
                "round finished but no round result found",
            )
        logger.info(f"game {game_id}: round ended")
        process_round_end(game_state, round_result)

        if check_game_end(game_state):
            bot_controller = self._bot_controllers.get(game_id)
            bot_seats = bot_controller.bot_seats if bot_controller else None
            game_result = finalize_game(game_state, bot_seats=bot_seats)
            logger.info(f"game {game_id}: game ended")
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
        logger.info(f"game {game_id}: starting next round")
        init_round(game_state)

        bot_controller = self._bot_controllers[game_id]
        bot_seats = bot_controller.bot_seats

        events = self._create_round_started_events(game_state, bot_seats=bot_seats)

        round_state = game_state.round_state
        draw_events = process_draw_phase(round_state, game_state)
        events.extend(convert_events(draw_events))

        dealer_seat = round_state.dealer_seat
        if bot_controller.is_bot(dealer_seat):
            bot_events = await self._process_bot_followup(game_id)
            events.extend(bot_events)

        return events

    async def _process_bot_followup(self, game_id: str) -> list[ServiceEvent]:
        """
        Process bot turn actions iteratively.

        Loop until a human player's turn is reached, a pending call prompt
        awaits human input, or the round ends.
        """
        all_events: list[ServiceEvent] = []
        bot_controller = self._bot_controllers.get(game_id)
        game_state = self._games.get(game_id)
        if bot_controller is None or game_state is None:
            return all_events

        for _ in range(100):  # safety limit
            round_state = game_state.round_state
            if round_state.phase != RoundPhase.PLAYING:
                break
            if round_state.pending_call_prompt is not None:
                break  # waiting for human caller

            current_seat = round_state.current_player_seat
            if not bot_controller.is_bot(current_seat):
                break

            action_data = bot_controller.get_turn_action(current_seat, round_state)
            if action_data is None:
                break

            action, data = action_data
            events = await self._dispatch_and_process(game_id, current_seat, action, data)
            all_events.extend(events)

        return all_events
