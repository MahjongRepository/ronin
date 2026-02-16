"""
MahjongGameService implementation for the Mahjong game.

Orchestrates game logic, AI player turns, and event generation for the session manager.
The service manages state transitions while action handlers are pure functions
that return new state.
"""

import logging
from typing import Any

from pydantic import ValidationError

from game.logic.action_handlers import (
    TURN_ACTIONS,
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
from game.logic.action_result import ActionResult
from game.logic.ai_player import AIPlayer, AIPlayerStrategy
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import AIPlayerType, CallType, GameAction, GameErrorCode, RoundPhase, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    ErrorEvent,
    EventType,
    FuritenEvent,
    GameEndedEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
    ServiceEvent,
    convert_events,
    extract_round_result,
    parse_wire_target,
)
from game.logic.exceptions import InvalidActionError, InvalidGameActionError, UnsupportedSettingsError
from game.logic.game import (
    check_game_end,
    finalize_game,
    init_game,
    init_round,
    process_round_end,
)
from game.logic.matchmaker import fill_seats
from game.logic.rng import generate_seed
from game.logic.round_advance import RoundAdvanceManager
from game.logic.service import GameService
from game.logic.settings import GameSettings
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

logger = logging.getLogger(__name__)

# Safety limits for AI player processing loops
MAX_AI_PLAYER_TURN_ITERATIONS = 100
MAX_AI_PLAYER_CALL_ITERATIONS = 10

_AI_PLAYER_TYPE_TO_STRATEGY: dict[AIPlayerType, AIPlayerStrategy] = {
    AIPlayerType.TSUMOGIRI: AIPlayerStrategy.TSUMOGIRI,
}


class MahjongGameService(GameService):
    """
    Game service for Mahjong implementing the GameService interface.

    Maintains game states for multiple concurrent games.
    """

    def __init__(self, *, auto_cleanup: bool = True, settings: GameSettings | None = None) -> None:
        self._games: dict[str, MahjongGameState] = {}
        self._ai_player_controllers: dict[str, AIPlayerController] = {}
        self._furiten_state: dict[str, dict[int, bool]] = {}
        self._round_advance = RoundAdvanceManager()
        self._auto_cleanup = auto_cleanup
        self._settings = settings

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> list[ServiceEvent]:
        """
        Start a new mahjong game with the given players.

        Uses matchmaker to assign seats randomly and fill with AI players.
        Returns initial state events for each player.
        When seed is provided, the game is deterministically reproducible.
        When seed is None, a random seed is generated.
        When wall is provided, use it instead of generating from seed.
        """
        game_seed = seed if seed is not None else generate_seed()
        if not isinstance(game_seed, str):
            return self._create_error_event(
                GameErrorCode.INVALID_ACTION,
                f"Seed must be a string, got {type(game_seed).__name__}",
            )
        logger.info(f"starting game {game_id} with players: {player_names}")

        game_settings = settings or self._settings
        try:
            seat_configs = fill_seats(player_names, seed=game_seed)
            frozen_game = init_game(seat_configs, seed=game_seed, settings=game_settings, wall=wall)
        except (UnsupportedSettingsError, ValueError) as e:
            return self._create_error_event(GameErrorCode.INVALID_ACTION, str(e))
        self._games[game_id] = frozen_game

        self._furiten_state[game_id] = dict.fromkeys(range(4), False)

        ai_players: dict[int, AIPlayer] = {}
        for seat, config in enumerate(seat_configs):
            if config.ai_player_type is not None:
                strategy = _AI_PLAYER_TYPE_TO_STRATEGY.get(config.ai_player_type, AIPlayerStrategy.TSUMOGIRI)
                ai_players[seat] = AIPlayer(strategy=strategy)

        ai_player_controller = AIPlayerController(ai_players)
        self._ai_player_controllers[game_id] = ai_player_controller

        events: list[ServiceEvent] = []
        events.append(
            self._create_game_started_event(
                game_id, frozen_game, ai_player_seats=ai_player_controller.ai_player_seats
            )
        )
        events.extend(self._create_round_started_events(frozen_game))

        _new_round_state, new_game_state, draw_events = process_draw_phase(
            frozen_game.round_state, frozen_game
        )
        self._games[game_id] = new_game_state
        events.extend(convert_events(draw_events))

        # process AI player turns if dealer is an AI player
        dealer_seat = new_game_state.round_state.dealer_seat
        if ai_player_controller.is_ai_player(dealer_seat):
            ai_player_events = await self._process_ai_player_followup(game_id)
            events.extend(ai_player_events)

        return events

    def _create_game_started_event(
        self, game_id: str, game_state: MahjongGameState, ai_player_seats: set[int] | None = None
    ) -> ServiceEvent:
        """Create a single game_started event broadcast to all players."""
        players = [
            GamePlayerInfo(
                seat=p.seat,
                name=p.name,
                is_ai_player=p.seat in (ai_player_seats or set()),
            )
            for p in game_state.round_state.players
        ]
        return ServiceEvent(
            event=EventType.GAME_STARTED,
            data=GameStartedEvent(
                game_id=game_id,
                players=players,
                dealer_seat=game_state.round_state.dealer_seat,
                dealer_dice=game_state.dealer_dice,
            ),
            target=BroadcastTarget(),
        )

    def _create_round_started_events(self, game_state: MahjongGameState) -> list[ServiceEvent]:
        """Create round_started events for all players."""
        return [
            ServiceEvent(
                event=EventType.ROUND_STARTED,
                data=RoundStartedEvent(
                    **get_player_view(game_state, seat).model_dump(),
                    target=f"seat_{seat}",
                ),
                target=SeatTarget(seat=seat),
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

        Processes the action and triggers AI player turns as needed.
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

        # turn actions are never valid while a call prompt is pending
        if game_state.round_state.pending_call_prompt is not None and action in TURN_ACTIONS:
            raise InvalidGameActionError(
                action=action.value,
                seat=seat,
                reason="cannot perform turn action while a call prompt is pending",
            )

        events = await self._dispatch_and_process(game_id, seat, action, data)

        # trigger AI player followup if round is playing and no pending callers
        # Re-fetch state safely: game may have been cleaned up during game-end handling
        game_state = self._games.get(game_id)
        if game_state is None:
            return events
        round_state = game_state.round_state
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            ai_player_events = await self._process_ai_player_followup(game_id)
            events.extend(ai_player_events)

        return events

    async def _dispatch_and_process(
        self, game_id: str, seat: int, action: GameAction, data: dict[str, Any]
    ) -> list[ServiceEvent]:
        """
        Dispatch action to handler and process result.

        Updates stored state from ActionResult.new_game_state. Does NOT trigger
        AI player followup to avoid recursion - AI player followup is handled by the top-level caller.
        """
        game_state = self._games[game_id]

        try:
            result = self._dispatch_action(game_state, seat, action, data)
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

    def _dispatch_action(  # noqa: PLR0911, C901
        self,
        game_state: MahjongGameState,
        seat: int,
        action: GameAction,
        data: dict[str, Any] | None = None,
    ) -> ActionResult | None:
        """Dispatch a game action to the appropriate handler.

        Single entry point for all synchronous action dispatch -- used by both
        player action processing and AI player call response handling.

        CONFIRM_ROUND is handled separately by the async confirmation path.

        Returns None for unknown actions.
        """
        round_state = game_state.round_state

        # No-data actions
        if action == GameAction.DECLARE_TSUMO:
            return handle_tsumo(round_state, game_state, seat)
        if action == GameAction.CALL_RON:
            return handle_ron(round_state, game_state, seat)
        if action == GameAction.CALL_KYUUSHU:
            return handle_kyuushu(round_state, game_state, seat)
        if action == GameAction.PASS:
            return handle_pass(round_state, game_state, seat)

        # Data actions
        if data is None:
            data = {}
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

    def _update_state_from_result(self, game_id: str, result: ActionResult) -> None:
        """Update stored state from ActionResult if new state was returned."""
        if result.new_game_state is not None:
            self._games[game_id] = result.new_game_state

    async def _process_action_result_internal(self, game_id: str, result: ActionResult) -> list[ServiceEvent]:
        """
        Process action result without triggering AI player followup.

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

        # dispatch AI player call responses through standard handlers
        self._dispatch_ai_player_call_responses(game_id, events)

        # Re-fetch state after AI player responses
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # if player callers still pending, wait
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

    def get_game_seed(self, game_id: str) -> str | None:
        """Return the seed for a game, or None if game doesn't exist."""
        game_state = self._games.get(game_id)
        return game_state.seed if game_state is not None else None

    def is_round_advance_pending(self, game_id: str) -> bool:
        """Check if a round advance is waiting for player confirmation."""
        return self._round_advance.is_pending(game_id)

    def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
        """Return player names that still need to confirm round advance."""
        state = self._games.get(game_id)
        if state is None:
            return []
        remaining = self._round_advance.get_unconfirmed_seats(game_id)
        if not remaining:
            return []
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
        raise InvalidActionError(f"Unknown timeout type: {timeout_type}")

    async def _handle_turn_timeout(
        self, game_id: str, game_state: MahjongGameState, player_name: str, seat: int
    ) -> list[ServiceEvent]:
        """Handle TURN timeout: tsumogiri (discard the last tile in hand)."""
        player = game_state.round_state.players[seat]
        if game_state.round_state.current_player_seat != seat or not player.tiles:
            return []
        if game_state.round_state.pending_call_prompt is not None:
            return []
        tile_id = player.tiles[-1]
        try:
            return await self.handle_action(game_id, player_name, GameAction.DISCARD, {"tile_id": tile_id})
        except InvalidGameActionError as e:
            if e.seat != seat:
                raise
            logger.warning(
                f"game {game_id}: turn timeout for '{player_name}' seat {seat} "
                f"hit InvalidGameActionError (race condition), ignoring"
            )
            return []

    async def _handle_meld_timeout(
        self, game_id: str, game_state: MahjongGameState, player_name: str, seat: int
    ) -> list[ServiceEvent]:
        """Handle MELD timeout: pass on the call opportunity.

        Lets InvalidGameActionError propagate to the session manager for disconnect handling.
        A meld timeout PASS can trigger prompt resolution, which may fail if another caller
        previously submitted invalid data (defense-in-depth safety net). The session manager
        must handle disconnect + AI player replacement for the offending seat.
        """
        prompt = game_state.round_state.pending_call_prompt
        if prompt is None or seat not in prompt.pending_seats:
            return []
        return await self.handle_action(game_id, player_name, GameAction.PASS, {})

    def _find_player_seat_frozen(
        self, game_id: str, game_state: MahjongGameState, player_name: str
    ) -> int | None:
        """Find the seat number for a player by name."""
        ai_player_controller = self._ai_player_controllers.get(game_id)
        for player in game_state.round_state.players:
            if player.name == player_name:
                if ai_player_controller and ai_player_controller.is_ai_player(player.seat):
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
                target=parse_wire_target(target),
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

        Uses the pending call prompt system: dispatches AI player responses through handlers,
        waits for player callers, or advances turn if no callers.
        """
        # check if round ended immediately (abortive draws)
        round_end_events = await self._check_and_handle_round_end(game_id, events)
        if round_end_events is not None:
            return round_end_events

        # Re-fetch state after potential updates
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.pending_call_prompt is not None:
            # dispatch AI player call responses through handlers
            self._dispatch_ai_player_call_responses(game_id, events)

            # Re-fetch state after AI player responses
            game_state = self._games[game_id]
            round_state = game_state.round_state

            # if player callers still pending, wait
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

    def _dispatch_ai_player_call_responses(self, game_id: str, events: list[ServiceEvent]) -> None:
        """
        Dispatch AI player responses to pending call prompt.

        Each AI player's response goes through the same handler functions as player
        responses. Resolution happens when all callers respond.
        Updates stored state from each handler result.
        """
        ai_player_controller = self._ai_player_controllers[game_id]

        # Process AI player responses one at a time, re-fetching state each time
        for _ in range(MAX_AI_PLAYER_CALL_ITERATIONS):
            game_state = self._games[game_id]
            round_state = game_state.round_state
            prompt = round_state.pending_call_prompt
            if prompt is None:
                break  # resolved

            # Find next AI player that needs to respond
            ai_player_seats = [
                s for s in sorted(prompt.pending_seats) if ai_player_controller.is_ai_player(s)
            ]
            if not ai_player_seats:
                break  # No more AI players to respond

            seat = ai_player_seats[0]
            caller_info = self._find_caller_info(prompt, seat)
            response = ai_player_controller.get_call_response(
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

            result = self._dispatch_ai_player_call_action(game_id, game_state, seat, action, data)
            if result is None:
                break
            self._update_state_from_result(game_id, result)
            events.extend(convert_events(result.events))

    def _try_ai_player_dispatch(  # noqa: PLR0913
        self,
        game_state: MahjongGameState,
        game_id: str,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
        label: str,
    ) -> ActionResult | None:
        """Attempt an AI player dispatch, returning None on own-seat failure.

        Re-raises InvalidGameActionError if the error blames a different seat
        (e.g. resolution failed on a player's prior invalid data).
        """
        try:
            return self._dispatch_action(game_state, seat, action, data)
        except InvalidGameActionError as e:
            if e.seat != seat:
                raise
            logger.exception(f"game {game_id}: AI player at seat {seat} {label} action={action}")
            return None

    def _dispatch_ai_player_call_action(
        self,
        game_id: str,
        game_state: MahjongGameState,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> ActionResult | None:
        """Dispatch an AI player call response, falling back to PASS on failure.

        Returns ActionResult on success, or None if both the original action
        and the PASS fallback fail. Re-raises if the error blames a different
        seat (e.g. resolution failed on a player's prior invalid data).
        """
        label = "call failed, falling back to PASS"
        result = self._try_ai_player_dispatch(game_state, game_id, seat, action, data, label)
        if result is not None:
            return result
        if action == GameAction.PASS:
            return None
        return self._try_ai_player_dispatch(
            game_state,
            game_id,
            seat,
            GameAction.PASS,
            {},
            "PASS fallback also failed",
        )

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
            frozen_game, game_result = finalize_game(frozen_game)
            logger.info(f"game {game_id}: game ended")
            # Always store finalized state before cleanup decision
            self._games[game_id] = frozen_game

            if self._auto_cleanup:
                self.cleanup_game(game_id)
            return [
                ServiceEvent(
                    event=EventType.GAME_END,
                    data=GameEndedEvent(
                        winner_seat=game_result.winner_seat,
                        standings=game_result.standings,
                        target="all",
                    ),
                    target=BroadcastTarget(),
                )
            ]

        # Store updated state
        self._games[game_id] = frozen_game

        # enter waiting state for round confirmation
        ai_player_controller = self._ai_player_controllers.get(game_id)
        ai_player_seats = ai_player_controller.ai_player_seats if ai_player_controller else set()
        if self._round_advance.setup_pending(game_id, ai_player_seats):
            # all AI players (no players) -- advance immediately
            return await self._start_next_round(game_id)

        # return empty -- the RoundEndEvent is already in the caller's events list
        return []

    async def _handle_confirm_round(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """Handle a player confirming readiness for the next round."""
        result = self._round_advance.confirm_seat(game_id, seat)
        if result is None:
            return self._create_error_event(
                GameErrorCode.INVALID_ACTION,
                "no round pending confirmation",
                target=f"seat_{seat}",
            )

        if not result:
            return []  # still waiting for other players

        # all confirmed -- start next round
        # _start_next_round already handles AI player dealer followup
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
                        target=SeatTarget(seat=seat),
                    )
                )

        self._furiten_state[game_id] = furiten_state
        return events

    def cleanup_game(self, game_id: str) -> None:
        """Remove all game state for a game that was abandoned or cleaned up externally."""
        self._games.pop(game_id, None)
        self._ai_player_controllers.pop(game_id, None)
        self._furiten_state.pop(game_id, None)
        self._round_advance.cleanup_game(game_id)

    def replace_with_ai_player(self, game_id: str, player_name: str) -> None:
        """
        Replace a disconnected player with an AI player at their seat.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return

        # find seat BEFORE registering AI player (_find_player_seat skips AI player seats)
        seat = self._find_player_seat_frozen(game_id, game_state, player_name)
        if seat is None:
            return

        ai_player_controller = self._ai_player_controllers.get(game_id)
        if ai_player_controller is None:
            return

        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        ai_player_controller.add_ai_player(seat, ai_player)
        logger.info(f"game {game_id}: replaced '{player_name}' (seat {seat}) with AI player")

    async def _auto_confirm_pending_advance(self, game_id: str, seat: int) -> list[ServiceEvent] | None:
        """Auto-confirm a seat's pending round advance after AI player replacement.

        Returns events if the pending advance was handled, None if not applicable.
        """
        if not self._round_advance.is_seat_required(game_id, seat):
            return None
        return await self._handle_confirm_round(game_id, seat)

    async def process_ai_player_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Process pending AI player actions after a player was replaced with an AI player at the given seat.
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

        # if the replaced player had a pending call prompt, resolve their response as AI player
        prompt = round_state.pending_call_prompt
        if prompt is not None and seat in prompt.pending_seats:
            self._dispatch_ai_player_call_responses(game_id, events)

            # Re-fetch state after AI player responses
            game_state = self._games[game_id]
            round_state = game_state.round_state

            if round_state.pending_call_prompt is not None:
                # other player callers still pending
                return events

            # prompt fully resolved - check round end
            round_end_events = await self._check_and_handle_round_end(game_id, events)
            if round_end_events is not None:
                return round_end_events

        # Re-fetch state
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # process AI player turns if current player is an AI player
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            ai_player_events = await self._process_ai_player_followup(game_id)
            events.extend(ai_player_events)

        return events

    async def _start_next_round(self, game_id: str) -> list[ServiceEvent]:
        """Start the next round and return events."""
        frozen_game = self._games[game_id]
        logger.info(f"game {game_id}: starting next round")

        frozen_game = init_round(frozen_game)
        self._games[game_id] = frozen_game

        self._furiten_state[game_id] = dict.fromkeys(range(4), False)

        ai_player_controller = self._ai_player_controllers[game_id]

        events = self._create_round_started_events(frozen_game)

        _new_round_state, new_game_state, draw_events = process_draw_phase(
            frozen_game.round_state, frozen_game
        )
        self._games[game_id] = new_game_state
        events.extend(convert_events(draw_events))

        dealer_seat = new_game_state.round_state.dealer_seat
        if ai_player_controller.is_ai_player(dealer_seat):
            ai_player_events = await self._process_ai_player_followup(game_id)
            events.extend(ai_player_events)

        return events

    async def _process_ai_player_followup(self, game_id: str) -> list[ServiceEvent]:
        """
        Process AI player turn actions iteratively.

        Loop until a player's turn is reached, a pending call prompt
        awaits player input, or the round ends.
        """
        all_events: list[ServiceEvent] = []
        ai_player_controller = self._ai_player_controllers.get(game_id)
        if ai_player_controller is None:
            return all_events

        for _ in range(MAX_AI_PLAYER_TURN_ITERATIONS):
            # Re-fetch state each iteration as it may have been updated
            game_state = self._games.get(game_id)
            if game_state is None:
                break

            round_state = game_state.round_state
            if round_state.phase != RoundPhase.PLAYING:
                break
            if round_state.pending_call_prompt is not None:
                break  # waiting for player caller

            current_seat = round_state.current_player_seat
            if not ai_player_controller.is_ai_player(current_seat):
                break

            events = await self._execute_ai_player_turn(game_id, ai_player_controller, current_seat)
            if events is None:
                break
            all_events.extend(events)

        return all_events

    async def _try_ai_player_dispatch_async(
        self,
        game_id: str,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
        label: str,
    ) -> list[ServiceEvent] | None:
        """Attempt an async AI player dispatch, returning None on own-seat failure.

        Re-raises InvalidGameActionError if the error blames a different seat.
        """
        try:
            return await self._dispatch_and_process(game_id, seat, action, data)
        except InvalidGameActionError as e:
            if e.seat != seat:
                raise
            logger.exception(f"game {game_id}: AI player at seat {seat} {label} action={action}")
            return None

    async def _execute_ai_player_turn(
        self, game_id: str, ai_player_controller: AIPlayerController, seat: int
    ) -> list[ServiceEvent] | None:
        """Execute a single AI player turn action, falling back to tsumogiri on failure.

        Returns events on success, or None if the AI player has no action or all fallbacks fail.
        Re-raises InvalidGameActionError when the error blames a different seat (player).
        """
        round_state = self._games[game_id].round_state
        action_data = ai_player_controller.get_turn_action(seat, round_state)
        if action_data is None:
            return None

        action, data = action_data
        result = await self._try_ai_player_dispatch_async(
            game_id, seat, action, data, "turn failed, falling back to tsumogiri"
        )
        if result is not None:
            return result
        return await self._ai_player_tsumogiri_fallback(game_id, seat)

    async def _ai_player_tsumogiri_fallback(self, game_id: str, seat: int) -> list[ServiceEvent] | None:
        """Fallback to tsumogiri (discard last tile) when an AI player's turn action fails.

        Returns events on success, or None if the fallback also fails.
        """
        fallback_state = self._games.get(game_id)
        if fallback_state is None:
            return None
        fallback_player = fallback_state.round_state.players[seat]
        if not fallback_player.tiles:
            return None
        return await self._try_ai_player_dispatch_async(
            game_id,
            seat,
            GameAction.DISCARD,
            {"tile_id": fallback_player.tiles[-1]},
            "tsumogiri fallback also failed",
        )
