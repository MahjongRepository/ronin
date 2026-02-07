"""
MahjongGameService implementation for the Mahjong game.

Orchestrates game logic, bot turns, and event generation for the session manager.
The service manages state transitions while action handlers are pure functions
that return new state.
"""

import logging
import random
from dataclasses import dataclass
from dataclasses import field as dataclass_field
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
from game.logic.enums import BotType, CallType, GameAction, GameErrorCode, RoundPhase, TimeoutType
from game.logic.game import (
    check_game_end,
    finalize_game,
    init_game,
    init_round,
    process_round_end,
)
from game.logic.matchmaker import fill_seats
from game.logic.service import GameService
from game.logic.state import (
    MahjongGameState,
    PendingCallPrompt,
    get_player_view,
)
from game.logic.turn import (
    process_draw_phase,
)
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
from game.logic.win import is_effective_furiten
from game.messaging.events import (
    CallPromptEvent,
    ErrorEvent,
    EventType,
    FuritenEvent,
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


@dataclass
class PendingRoundAdvance:
    """Tracks which players have confirmed readiness for the next round."""

    confirmed_seats: set[int] = dataclass_field(default_factory=set)
    required_seats: set[int] = dataclass_field(default_factory=set)  # human seats only

    @property
    def all_confirmed(self) -> bool:
        return self.required_seats.issubset(self.confirmed_seats)


class MahjongGameService(GameService):
    """
    Game service for Mahjong implementing the GameService interface.

    Maintains game states for multiple concurrent games.
    """

    def __init__(self, *, auto_cleanup: bool = True) -> None:
        self._games: dict[str, MahjongGameState] = {}
        self._bot_controllers: dict[str, BotController] = {}
        self._furiten_state: dict[str, dict[int, bool]] = {}
        self._pending_advances: dict[str, PendingRoundAdvance] = {}
        self._auto_cleanup = auto_cleanup

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: float | None = None,
    ) -> list[ServiceEvent]:
        """
        Start a new mahjong game with the given players.

        Uses matchmaker to assign seats randomly and fill with bots.
        Returns initial state events for each player.
        When seed is provided, the game is deterministically reproducible.
        When seed is None, a random seed is generated.
        """
        game_seed = seed if seed is not None else random.random()  # noqa: S311
        logger.info(f"starting game {game_id} with players: {player_names}")
        seat_configs = fill_seats(player_names, seed=game_seed)

        frozen_game = init_game(seat_configs, seed=game_seed)
        self._games[game_id] = frozen_game

        self._furiten_state[game_id] = dict.fromkeys(range(4), False)

        bots: dict[int, BotPlayer] = {}
        for seat, config in enumerate(seat_configs):
            if config.bot_type is not None:
                strategy = _BOT_TYPE_TO_STRATEGY.get(config.bot_type, BotStrategy.TSUMOGIRI)
                bots[seat] = BotPlayer(strategy=strategy)

        bot_controller = BotController(bots)
        self._bot_controllers[game_id] = bot_controller

        events: list[ServiceEvent] = []
        events.append(
            self._create_game_started_event(game_id, frozen_game, bot_seats=bot_controller.bot_seats)
        )
        events.extend(self._create_round_started_events(frozen_game, bot_seats=bot_controller.bot_seats))

        _new_round_state, new_game_state, draw_events = process_draw_phase(
            frozen_game.round_state, frozen_game
        )
        self._games[game_id] = new_game_state
        events.extend(convert_events(draw_events))

        # process bot turns if dealer is a bot
        dealer_seat = new_game_state.round_state.dealer_seat
        if bot_controller.is_bot(dealer_seat):
            bot_events = await self._process_bot_followup(game_id)
            events.extend(bot_events)

        return events

    def _create_game_started_event(
        self, game_id: str, game_state: MahjongGameState, bot_seats: set[int] | None = None
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
            data=GameStartedEvent(game_id=game_id, players=players),
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
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Handle a game action from a player.

        Processes the action and triggers bot turns as needed.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            # debug level: this is expected for confirm_round after game ends (race condition)
            logger.debug(f"game {game_id}: action from '{player_name}' but game not found")
            return self._create_error_event(GameErrorCode.GAME_ERROR, "game not found")

        seat = self._find_player_seat_frozen(game_id, game_state, player_name)
        if seat is None:
            logger.warning(f"game {game_id}: action from '{player_name}' but player not in game")
            return self._create_error_event(GameErrorCode.GAME_ERROR, "player not in game")

        logger.info(f"game {game_id}: player '{player_name}' (seat {seat}) action={action}")

        # handle confirm_round before dispatching to game logic
        if action == GameAction.CONFIRM_ROUND:
            return await self._handle_confirm_round(game_id, seat)

        # reject game actions when the round is not in progress
        if game_state.round_state.phase != RoundPhase.PLAYING:
            return self._create_error_event(
                GameErrorCode.INVALID_ACTION, "round is not in progress", target=f"seat_{seat}"
            )

        events = await self._dispatch_and_process(game_id, seat, action, data)

        # trigger bot followup if round is playing and no pending callers
        # Re-fetch state safely: game may have been cleaned up during game-end handling
        game_state = self._games.get(game_id)
        if game_state is None:
            return events
        round_state = game_state.round_state
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            bot_events = await self._process_bot_followup(game_id)
            events.extend(bot_events)

        return events

    async def _dispatch_and_process(
        self, game_id: str, seat: int, action: GameAction, data: dict[str, Any]
    ) -> list[ServiceEvent]:
        """
        Dispatch action to handler and process result.

        Updates stored state from ActionResult.new_game_state. Does NOT trigger
        bot followup to avoid recursion - bot followup is handled by the top-level caller.
        """
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # actions without data parameters
        no_data_handlers = {
            GameAction.DECLARE_TSUMO: lambda: handle_tsumo(round_state, game_state, seat),
            GameAction.CALL_RON: lambda: handle_ron(round_state, game_state, seat),
            GameAction.CALL_KYUUSHU: lambda: handle_kyuushu(round_state, game_state, seat),
            GameAction.PASS: lambda: handle_pass(round_state, game_state, seat),
        }

        handler = no_data_handlers.get(action)
        if handler is not None:
            result = handler()
            self._update_state_from_result(game_id, result)
            events = await self._process_action_result_internal(game_id, result)
            return self._append_furiten_changes(game_id, events)

        # actions with data parameters
        try:
            result = self._execute_data_action(game_state, seat, action, data)
        except ValidationError as e:
            logger.warning(f"game {game_id}: validation error for seat {seat} action={action}: {e}")
            return self._create_error_event(
                GameErrorCode.VALIDATION_ERROR,
                f"invalid action data: {e}",
                target=f"seat_{seat}",
            )

        if result is None:
            logger.warning(f"game {game_id}: unknown action '{action}' from seat {seat}")
            return self._create_error_event(
                GameErrorCode.UNKNOWN_ACTION,
                f"unknown action: {action}",
                target=f"seat_{seat}",
            )

        self._update_state_from_result(game_id, result)
        events = await self._process_action_result_internal(game_id, result)
        return self._append_furiten_changes(game_id, events)

    def _update_state_from_result(self, game_id: str, result: ActionResult) -> None:
        """Update stored state from ActionResult if new state was returned."""
        if result.new_game_state is not None:
            self._games[game_id] = result.new_game_state

    def _execute_data_action(
        self, game_state: MahjongGameState, seat: int, action: GameAction, data: dict[str, Any]
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
            return await self._handle_chankan_prompt(game_id, events)

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
    ) -> list[ServiceEvent]:
        """Handle chankan prompt using the pending call prompt system."""
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.pending_call_prompt is None:
            return events

        # dispatch bot call responses through standard handlers
        self._dispatch_bot_call_responses(game_id, events)

        # Re-fetch state after bot responses
        game_state = self._games[game_id]
        round_state = game_state.round_state

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
        return self._find_player_seat_frozen(game_id, game_state, player_name)

    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        """Return the current game state, or None if game doesn't exist."""
        return self._games.get(game_id)

    def is_round_advance_pending(self, game_id: str) -> bool:
        """Check if a round advance is waiting for human confirmation."""
        return game_id in self._pending_advances

    def get_pending_round_advance_human_names(self, game_id: str) -> list[str]:
        """Return human player names that still need to confirm round advance."""
        pending = self._pending_advances.get(game_id)
        state = self._games.get(game_id)
        if pending is None or state is None:
            return []
        remaining = pending.required_seats - pending.confirmed_seats
        return [p.name for p in state.round_state.players if p.seat in remaining]

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
        For ROUND_ADVANCE timeout: auto-confirm round advancement.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        seat = self._find_player_seat_frozen(game_id, game_state, player_name)
        if seat is None:
            return []

        if timeout_type == TimeoutType.TURN:
            return await self._handle_turn_timeout(game_id, game_state, player_name, seat)
        if timeout_type == TimeoutType.MELD:
            return await self._handle_meld_timeout(game_id, game_state, player_name, seat)
        if timeout_type == TimeoutType.ROUND_ADVANCE:
            return await self._handle_confirm_round(game_id, seat)

        logger.error(f"game {game_id}: unknown timeout type '{timeout_type}' for player '{player_name}'")
        raise ValueError(f"Unknown timeout type: {timeout_type}")

    async def _handle_turn_timeout(
        self, game_id: str, game_state: MahjongGameState, player_name: str, seat: int
    ) -> list[ServiceEvent]:
        """Handle TURN timeout: tsumogiri (discard the last tile in hand)."""
        player = game_state.round_state.players[seat]
        if game_state.round_state.current_player_seat != seat or not player.tiles:
            return []
        tile_id = player.tiles[-1]
        return await self.handle_action(game_id, player_name, GameAction.DISCARD, {"tile_id": tile_id})

    async def _handle_meld_timeout(
        self, game_id: str, game_state: MahjongGameState, player_name: str, seat: int
    ) -> list[ServiceEvent]:
        """Handle MELD timeout: pass on the call opportunity."""
        prompt = game_state.round_state.pending_call_prompt
        if prompt is None or seat not in prompt.pending_seats:
            return []
        return await self.handle_action(game_id, player_name, GameAction.PASS, {})

    def _find_player_seat_frozen(
        self, game_id: str, game_state: MahjongGameState, player_name: str
    ) -> int | None:
        """Find the seat number for a human player by name."""
        bot_controller = self._bot_controllers.get(game_id)
        for player in game_state.round_state.players:
            if player.name == player_name:
                if bot_controller and bot_controller.is_bot(player.seat):
                    continue
                return player.seat
        return None

    def _create_error_event(
        self, code: GameErrorCode, message: str, target: str = "all"
    ) -> list[ServiceEvent]:
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
        # check if round ended immediately
        round_end_events = await self._check_and_handle_round_end(game_id, events)
        if round_end_events is not None:
            return round_end_events

        # Re-fetch state after potential updates
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.pending_call_prompt is not None:
            # dispatch bot call responses through handlers
            self._dispatch_bot_call_responses(game_id, events)

            # Re-fetch state after bot responses
            game_state = self._games[game_id]
            round_state = game_state.round_state

            # if human callers still pending, wait
            if round_state.pending_call_prompt is not None:
                return events

            # prompt resolved - check round end
            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events
        elif round_state.phase == RoundPhase.PLAYING:
            # no callers - draw for next player (turn already advanced by process_discard_phase)
            _new_round_state, new_game_state, draw_events = process_draw_phase(round_state, game_state)
            self._games[game_id] = new_game_state

            events.extend(convert_events(draw_events))

            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events

        return events

    def _dispatch_bot_call_responses(self, game_id: str, events: list[ServiceEvent]) -> None:
        """
        Dispatch bot responses to pending call prompt.

        Each bot's response goes through the same handler functions as human
        responses. Resolution happens when all callers respond.
        Updates stored state from each handler result.
        """
        bot_controller = self._bot_controllers[game_id]

        # Process bot responses one at a time, re-fetching state each time
        for _ in range(10):  # Safety limit
            game_state = self._games[game_id]
            round_state = game_state.round_state
            prompt = round_state.pending_call_prompt
            if prompt is None:
                break  # resolved

            # Find next bot that needs to respond
            bot_seats = [s for s in sorted(prompt.pending_seats) if bot_controller.is_bot(s)]
            if not bot_seats:
                break  # No more bots to respond

            seat = bot_seats[0]
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

            result = self._call_handler(game_state, seat, action, data)
            self._update_state_from_result(game_id, result)
            events.extend(convert_events(result.events))

    def _call_handler(
        self,
        game_state: MahjongGameState,
        seat: int,
        action: GameAction,
        data: dict,
    ) -> ActionResult:
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
        raise AssertionError(f"unexpected action in _call_handler: {action}")  # pragma: no cover

    def _find_caller_info(self, prompt: PendingCallPrompt, seat: int) -> int | MeldCaller:
        """Find caller info for a seat from the prompt's callers list."""
        for caller in prompt.callers:
            caller_seat = caller if isinstance(caller, int) else caller.seat
            if caller_seat == seat:
                return caller
        raise AssertionError(f"seat {seat} not found in prompt callers")  # pragma: no cover

    async def _handle_round_end(
        self, game_id: str, round_result: RoundResult | None = None
    ) -> list[ServiceEvent]:
        """Handle the end of a round -- enter waiting state for confirmations."""
        frozen_game = self._games[game_id]

        if round_result is None:  # pragma: no cover - defensive check
            logger.error(f"game {game_id}: round finished but no round result found in events")
            return self._create_error_event(
                GameErrorCode.MISSING_ROUND_RESULT,
                "round finished but no round result found",
            )
        logger.info(f"game {game_id}: round ended")

        frozen_game = process_round_end(frozen_game, round_result)

        if check_game_end(frozen_game):
            bot_controller = self._bot_controllers.get(game_id)
            bot_seats = bot_controller.bot_seats if bot_controller else None
            frozen_game, game_result = finalize_game(frozen_game, bot_seats=bot_seats)
            logger.info(f"game {game_id}: game ended")
            # Always store finalized state before cleanup decision
            self._games[game_id] = frozen_game

            if self._auto_cleanup:
                self.cleanup_game(game_id)
            return [
                ServiceEvent(
                    event=EventType.GAME_END,
                    data=GameEndedEvent(result=game_result, target="all"),
                    target="all",
                )
            ]

        # Store updated state
        self._games[game_id] = frozen_game

        # enter waiting state for round confirmation
        bot_controller = self._bot_controllers.get(game_id)
        bot_seats = bot_controller.bot_seats if bot_controller else set()
        human_seats = {seat for seat in range(4) if seat not in bot_seats}

        pending = PendingRoundAdvance(
            confirmed_seats=set(bot_seats),  # bots auto-confirm
            required_seats=human_seats,
        )
        self._pending_advances[game_id] = pending

        # if all bots (no humans), advance immediately
        if pending.all_confirmed:
            self._pending_advances.pop(game_id, None)
            return await self._start_next_round(game_id)

        # return empty -- the RoundEndEvent is already in the caller's events list
        return []

    async def _handle_confirm_round(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """Handle a player confirming readiness for the next round."""
        pending = self._pending_advances.get(game_id)
        if pending is None:
            return self._create_error_event(
                GameErrorCode.INVALID_ACTION,
                "no round pending confirmation",
                target=f"seat_{seat}",
            )

        pending.confirmed_seats.add(seat)

        if not pending.all_confirmed:
            return []  # still waiting for other players

        # all confirmed -- start next round
        # _start_next_round already handles bot dealer followup
        self._pending_advances.pop(game_id, None)
        return await self._start_next_round(game_id)

    def _append_furiten_changes(self, game_id: str, events: list[ServiceEvent]) -> list[ServiceEvent]:
        """Append furiten state-change events if round is still playing."""
        game_state = self._games.get(game_id)
        if game_state is None:
            return events
        if game_state.round_state.phase == RoundPhase.PLAYING:
            events.extend(self._check_furiten_changes(game_id, list(range(4))))
        return events

    def _check_furiten_changes(self, game_id: str, seats: list[int]) -> list[ServiceEvent]:
        """
        Check if furiten state changed for the given seats and emit events.

        Only emits an event if the effective furiten state differs from the last known state.
        """
        game_state = self._games.get(game_id)
        if game_state is None or game_state.round_state.phase == RoundPhase.FINISHED:
            return []

        furiten_state = self._furiten_state.get(game_id, {})
        events: list[ServiceEvent] = []

        for seat in seats:
            player = game_state.round_state.players[seat]
            current = is_effective_furiten(player)
            previous = furiten_state.get(seat, False)

            if current != previous:
                furiten_state[seat] = current
                events.append(
                    ServiceEvent(
                        event=EventType.FURITEN,
                        data=FuritenEvent(
                            is_furiten=current,
                            target=f"seat_{seat}",
                        ),
                        target=f"seat_{seat}",
                    )
                )

        self._furiten_state[game_id] = furiten_state
        return events

    def cleanup_game(self, game_id: str) -> None:
        """Remove all game state for a game that was abandoned or cleaned up externally."""
        self._games.pop(game_id, None)
        self._bot_controllers.pop(game_id, None)
        self._furiten_state.pop(game_id, None)
        self._pending_advances.pop(game_id, None)

    def replace_player_with_bot(self, game_id: str, player_name: str) -> None:
        """
        Replace a human player with a bot at their seat.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return

        # find seat BEFORE registering bot (_find_player_seat skips bot seats)
        seat = self._find_player_seat_frozen(game_id, game_state, player_name)
        if seat is None:
            return

        bot_controller = self._bot_controllers.get(game_id)
        if bot_controller is None:
            return

        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        bot_controller.add_bot(seat, bot)
        logger.info(f"game {game_id}: replaced '{player_name}' (seat {seat}) with bot")

    async def _auto_confirm_pending_advance(self, game_id: str, seat: int) -> list[ServiceEvent] | None:
        """Auto-confirm a seat's pending round advance after bot replacement.

        Returns events if the pending advance was handled, None if not applicable.
        """
        pending = self._pending_advances.get(game_id)
        if pending is None or seat not in pending.required_seats:
            return None
        return await self._handle_confirm_round(game_id, seat)

    async def process_bot_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Process pending bot actions after a human was replaced with a bot at the given seat.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        # if there's a pending round advance, auto-confirm for the replaced player
        advance_events = await self._auto_confirm_pending_advance(game_id, seat)
        if advance_events is not None:
            return advance_events

        round_state = game_state.round_state
        if round_state.phase != RoundPhase.PLAYING:
            return []

        events: list[ServiceEvent] = []

        # if the replaced player had a pending call prompt, resolve their response as bot
        prompt = round_state.pending_call_prompt
        if prompt is not None and seat in prompt.pending_seats:
            self._dispatch_bot_call_responses(game_id, events)

            # Re-fetch state after bot responses
            game_state = self._games[game_id]
            round_state = game_state.round_state

            if round_state.pending_call_prompt is not None:
                # other human callers still pending
                return events

            # prompt fully resolved - check round end
            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events

        # Re-fetch state
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # process bot turns if current player is a bot
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            bot_events = await self._process_bot_followup(game_id)
            events.extend(bot_events)

        return events

    async def _start_next_round(self, game_id: str) -> list[ServiceEvent]:
        """Start the next round and return events."""
        frozen_game = self._games[game_id]
        logger.info(f"game {game_id}: starting next round")

        frozen_game = init_round(frozen_game)
        self._games[game_id] = frozen_game

        self._furiten_state[game_id] = dict.fromkeys(range(4), False)

        bot_controller = self._bot_controllers[game_id]
        bot_seats = bot_controller.bot_seats

        events = self._create_round_started_events(frozen_game, bot_seats=bot_seats)

        _new_round_state, new_game_state, draw_events = process_draw_phase(
            frozen_game.round_state, frozen_game
        )
        self._games[game_id] = new_game_state
        events.extend(convert_events(draw_events))

        dealer_seat = new_game_state.round_state.dealer_seat
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
        if bot_controller is None:
            return all_events

        for _ in range(100):  # safety limit
            # Re-fetch state each iteration as it may have been updated
            game_state = self._games.get(game_id)
            if game_state is None:
                break

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
