from typing import TYPE_CHECKING, Any

import structlog

from game.logic.action_handlers import (
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
from game.logic.action_result import create_draw_event
from game.logic.ai_player import AIPlayer, AIPlayerStrategy
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import AIPlayerType, CallType, GameAction, GameErrorCode, RoundPhase, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    ErrorEvent,
    EventType,
    GameEndedEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
    ServiceEvent,
    convert_events,
    extract_round_result,
    parse_event_target,
)
from game.logic.exceptions import GeneratedActionError, InvalidGameActionError
from game.logic.furiten_tracker import FuritenTracker
from game.logic.game import (
    check_game_end,
    finalize_game,
    init_game,
    init_round,
    process_round_end,
)
from game.logic.matchmaker import fill_seats
from game.logic.meld_compact import frozen_meld_to_compact
from game.logic.rng import generate_seed
from game.logic.round import choose_default_discard
from game.logic.round_advance import RoundAdvanceManager
from game.logic.service import GameService
from game.logic.settings import NUM_PLAYERS
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
    DiscardInfo,
    GamePlayerInfo,
    KanActionData,
    MeldCaller,
    PlayerReconnectState,
    PonActionData,
    ReconnectionSnapshot,
    RiichiActionData,
    RoundResult,
)
from game.logic.wall import tiles_remaining
from game.logic.win import is_effective_furiten

if TYPE_CHECKING:
    from game.logic.action_result import ActionResult
    from game.logic.settings import GameSettings

logger = structlog.get_logger()

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
        self._furiten_tracker = FuritenTracker()
        self._round_advance = RoundAdvanceManager()
        self._auto_cleanup = auto_cleanup
        self._settings = settings

    def start_game(
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

        Uses matchmaker to assign seats randomly and fill with AI players. Returns initial state events for each player.
        When seed is provided, the game is deterministically reproducible. When seed is None, a random seed is
        generated. When wall is provided, use it instead of generating from seed.
        """
        game_seed = seed if seed is not None else generate_seed()

        game_settings = settings or self._settings
        seat_configs = fill_seats(player_names, seed=game_seed)
        frozen_game = init_game(seat_configs, seed=game_seed, settings=game_settings, wall=wall)
        self._games[game_id] = frozen_game

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting game", player_names=player_names, hands=hands)

        self._furiten_tracker.init_game(game_id)

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
                game_id=game_id,
                game_state=frozen_game,
                ai_player_seats=ai_player_controller.ai_player_seats,
            ),
        )
        events.extend(self._create_round_started_events(frozen_game))

        _new_round_state, new_game_state, draw_events = process_draw_phase(
            frozen_game.round_state,
            frozen_game,
        )
        self._games[game_id] = new_game_state
        events.extend(convert_events(draw_events))

        # process AI player turns if dealer is an AI player
        dealer_seat = new_game_state.round_state.dealer_seat
        if ai_player_controller.is_ai_player(dealer_seat):
            ai_player_events = self._process_ai_player_followup(game_id)
            events.extend(ai_player_events)

        return events

    def _create_game_started_event(
        self,
        game_id: str,
        game_state: MahjongGameState,
        ai_player_seats: set[int] | None = None,
    ) -> ServiceEvent:
        """
        Create a single game_started event broadcast to all players.
        """
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
        """
        Create round_started events for all players.
        """
        events = []
        for seat in range(NUM_PLAYERS):
            view = get_player_view(game_state, seat)
            # Copy raw attribute values instead of using model_dump() to avoid
            # double-application of WireScore serializers on PlayerView.score.
            view_fields = {name: getattr(view, name) for name in type(view).model_fields}
            events.append(
                ServiceEvent(
                    event=EventType.ROUND_STARTED,
                    data=RoundStartedEvent(**view_fields, target=f"seat_{seat}"),
                    target=SeatTarget(seat=seat),
                ),
            )

        return events

    def handle_action(
        self,
        *,
        game_id: str,
        player_name: str,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Handle a game action from a player.

        Processes the action and triggers AI player turns as needed.
        """
        if self._games.get(game_id) is None:
            # debug level: this is expected for confirm_round after game ends (race condition)
            logger.debug("action but game not found")
            return self._create_error_event(code=GameErrorCode.GAME_ERROR, message="game not found")

        seat = self._find_player_seat(game_id, player_name)
        if seat is None:
            logger.warning("action but player not in game")
            return self._create_error_event(code=GameErrorCode.GAME_ERROR, message="player not in game")

        logger.debug("player action", action=action, action_data=data)

        # handle confirm_round before dispatching to game logic
        if action == GameAction.CONFIRM_ROUND:
            return self._handle_confirm_round(game_id, seat)

        game_state = self._games[game_id]

        # reject game actions when the round is not in progress
        if game_state.round_state.phase != RoundPhase.PLAYING:
            logger.warning(
                "action rejected: round not in progress",
                phase=game_state.round_state.phase.value,
                action=action.value,
            )
            return self._create_error_event(
                code=GameErrorCode.INVALID_ACTION,
                message="round is not in progress",
                target=f"seat_{seat}",
            )

        result = self._dispatch_action(game_state, seat=seat, action=action, data=data)
        events = self._commit_and_process(game_id, result)
        return self._continue_with_ai_players(game_id, events)

    def _continue_with_ai_players(self, game_id: str, events: list[ServiceEvent]) -> list[ServiceEvent]:
        """
        Run the AI players' turns after an action, when the round still plays and no call prompt waits.

        The game may be gone by now: a game end cleans it up.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return events

        round_state = game_state.round_state
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            events.extend(self._process_ai_player_followup(game_id))

        return events

    def _commit_and_process(self, game_id: str, result: ActionResult) -> list[ServiceEvent]:
        """
        Store a handler's result and run what follows it (round end, post-discard calls and draw, chankan).

        Does NOT trigger AI player turns, to avoid recursion: the top-level caller runs them. Anything raised from here
        on comes after the commit and is a server fault.
        """
        self._update_state_from_result(game_id, result)
        events = self._process_action_result_internal(game_id, result)
        return self._append_furiten_changes(game_id, events)

    def _dispatch_generated_action(
        self,
        game_id: str,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> ActionResult:
        """
        Dispatch an action the server made for a seat: an AI decision or a timeout default.

        The server generated it, so a refusal, structural or a soft ErrorEvent, is a server fault: raise
        GeneratedActionError, never kick the seat or count the refusal as progress.
        """
        try:
            result = self._dispatch_action(self._games[game_id], seat=seat, action=action, data=data)
        except InvalidGameActionError as e:
            raise GeneratedActionError(f"seat {seat} {action.value} refused: {e.reason}") from e

        error = next((e for e in result.events if isinstance(e, ErrorEvent)), None)
        if error is not None:
            raise GeneratedActionError(f"seat {seat} {action.value} refused: {error.code.value}: {error.message}")

        return result

    def _dispatch_action(  # noqa: PLR0911
        self,
        game_state: MahjongGameState,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> ActionResult:
        """
        Dispatch a game action to the appropriate handler.

        Single entry point for all action dispatch: player actions, AI decisions and timeout defaults.
        CONFIRM_ROUND is handled separately by the round confirmation path.
        """
        round_state = game_state.round_state
        match action:
            # No-data actions
            case GameAction.DECLARE_TSUMO:
                return handle_tsumo(round_state, game_state, seat=seat)
            case GameAction.CALL_RON:
                return handle_ron(round_state, game_state, seat=seat)
            case GameAction.CALL_KYUUSHU:
                return handle_kyuushu(round_state, game_state, seat=seat)
            case GameAction.PASS:
                return handle_pass(round_state, game_state, seat=seat)
            # Data actions
            case GameAction.DISCARD:
                return handle_discard(round_state, game_state, seat=seat, data=DiscardActionData(**data))
            case GameAction.DECLARE_RIICHI:
                return handle_riichi(round_state, game_state, seat=seat, data=RiichiActionData(**data))
            case GameAction.CALL_PON:
                return handle_pon(round_state, game_state, seat=seat, data=PonActionData(**data))
            case GameAction.CALL_CHI:
                return handle_chi(round_state, game_state, seat=seat, data=ChiActionData(**data))
            case GameAction.CALL_KAN:
                return handle_kan(round_state, game_state, seat=seat, data=KanActionData(**data))
            case _:  # pragma: no cover (exhaustive)
                raise AssertionError(f"action {action} has no handler")

    def _update_state_from_result(self, game_id: str, result: ActionResult) -> None:
        """
        Update stored state from ActionResult if new state was returned.
        """
        if result.new_game_state is not None:
            self._games[game_id] = result.new_game_state

    def _process_action_result_internal(self, game_id: str, result: ActionResult) -> list[ServiceEvent]:
        """
        Process action result without triggering AI player followup.

        Handles round end checking, post-discard processing, and chankan prompts.
        """
        events = convert_events(result.events)

        # check if round ended
        if self._check_and_handle_round_end(game_id, events):
            return events

        if result.needs_post_discard:
            return self._process_post_discard(game_id, events)

        # check for chankan prompt
        chankan_prompt = self._find_chankan_prompt(events)
        if chankan_prompt:
            return self._handle_chankan_prompt(game_id, events)

        return events

    def _find_chankan_prompt(self, events: list[ServiceEvent]) -> ServiceEvent | None:
        """
        Find a chankan call prompt in events.
        """
        return next(
            (e for e in events if isinstance(e.data, CallPromptEvent) and e.data.call_type == CallType.CHANKAN),
            None,
        )

    def _handle_chankan_prompt(
        self,
        game_id: str,
        events: list[ServiceEvent],
    ) -> list[ServiceEvent]:
        """
        Handle chankan prompt using the pending call prompt system.
        """
        prompt = self._games[game_id].round_state.pending_call_prompt
        if prompt is None:
            return events

        # dispatch AI player call responses through standard handlers
        self._dispatch_ai_player_call_responses(game_id, prompt, events)

        # Re-fetch state after AI player responses
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # if player callers still pending, wait
        if round_state.pending_call_prompt is not None:
            return events

        # resolved - check round end
        self._check_and_handle_round_end(game_id, events)
        return events

    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """
        Get the seat number for a player by name.
        """
        return self._find_player_seat(game_id, player_name)

    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        """
        Return the current game state, or None if game doesn't exist.
        """
        return self._games.get(game_id)

    def get_game_seed(self, game_id: str) -> str | None:
        """
        Return the seed for a game, or None if game doesn't exist.
        """
        game_state = self._games.get(game_id)
        return game_state.seed if game_state is not None else None

    def is_round_advance_pending(self, game_id: str) -> bool:
        """
        Check if a round advance is waiting for player confirmation.
        """
        return self._round_advance.is_pending(game_id)

    def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
        """
        Return player names that still need to confirm round advance.
        """
        state = self._games.get(game_id)
        if state is None:
            return []

        remaining = self._round_advance.get_unconfirmed_seats(game_id)
        if not remaining:
            return []

        return [p.name for p in state.round_state.players if p.seat in remaining]

    def handle_timeout(
        self,
        *,
        game_id: str,
        player_name: str,
        timeout_type: TimeoutType,
    ) -> list[ServiceEvent]:
        """
        Handle a player timeout by performing the default action.

        For TURN timeout: the default discard (the drawn tile unless kuikae forbids it).
        For MELD timeout: pass on the call opportunity.
        For ROUND_ADVANCE timeout: auto-confirm round advancement.
        """
        if self._games.get(game_id) is None:
            logger.warning("timeout for unknown game", game_id=game_id)
            return []

        seat = self._find_player_seat(game_id, player_name)
        if seat is None:
            logger.warning("timeout for unknown player")
            return []

        match timeout_type:
            case TimeoutType.TURN:
                return self._handle_turn_timeout(game_id, seat)
            case TimeoutType.MELD:
                return self._handle_meld_timeout(game_id, seat)
            case TimeoutType.ROUND_ADVANCE:
                return self._handle_round_advance_timeout(game_id, seat)
            case _:  # pragma: no cover (exhaustive)
                raise AssertionError(f"unknown timeout type: {timeout_type}")

    def _run_generated_action(
        self,
        game_id: str,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Run a timeout's default action for a seat, then the AI players' turns it leads to.
        """
        result = self._dispatch_generated_action(game_id, seat=seat, action=action, data=data)
        events = self._commit_and_process(game_id, result)
        return self._continue_with_ai_players(game_id, events)

    def _handle_turn_timeout(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """
        Handle TURN timeout: make the default discard (choose_default_discard).
        """
        round_state = self._games[game_id].round_state
        if round_state.phase != RoundPhase.PLAYING or round_state.current_player_seat != seat:
            logger.debug("turn timeout ignored: not the seat's turn")
            return []

        if round_state.pending_call_prompt is not None:
            logger.debug("turn timeout ignored: call prompt pending")
            return []

        tile_id = choose_default_discard(round_state.players[seat])
        logger.info("turn timeout, auto-discarding", tile_id=tile_id)
        return self._run_generated_action(game_id, seat=seat, action=GameAction.DISCARD, data={"tile_id": tile_id})

    def _handle_meld_timeout(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """
        Handle MELD timeout: pass on the call opportunity.
        """
        prompt = self._games[game_id].round_state.pending_call_prompt
        if prompt is None or seat not in prompt.pending_seats:
            return []

        logger.info("meld timeout, auto-passing")
        return self._run_generated_action(game_id, seat=seat, action=GameAction.PASS, data={})

    def _handle_round_advance_timeout(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """
        Handle ROUND_ADVANCE timeout: confirm the round end for the seat.

        The timer runs only while the seat's confirmation is pending, so finding none is a server fault.
        """
        if not self._round_advance.is_pending(game_id):
            raise GeneratedActionError(f"round advance timeout for seat {seat} with no round pending confirmation")

        return self._handle_confirm_round(game_id, seat)

    def _find_player_seat(
        self,
        game_id: str,
        player_name: str,
    ) -> int | None:
        """
        Find the seat number for a human player by name.

        Skips AI player seats so that human players are always found even if an AI player shares the same display name.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return None

        ai_player_controller = self._ai_player_controllers.get(game_id)
        for player in game_state.round_state.players:
            if player.name == player_name:
                if ai_player_controller and ai_player_controller.is_ai_player(player.seat):
                    continue

                return player.seat

        return None

    def _create_error_event(
        self,
        code: GameErrorCode,
        message: str,
        target: str = "all",
    ) -> list[ServiceEvent]:
        """
        Create an error event wrapped in a ServiceEvent.
        """
        return [
            ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(code=code, message=message, target=target),
                target=parse_event_target(target),
            ),
        ]

    def _check_and_handle_round_end(self, game_id: str, events: list[ServiceEvent]) -> bool:
        """
        Check if round has ended and handle accordingly.

        If the round is finished, appends round-end events to the events list and returns True. Returns False if the
        round is still in progress.
        """
        game_state = self._games[game_id]
        if game_state.round_state.phase != RoundPhase.FINISHED:
            return False

        result = extract_round_result(events)
        events.extend(self._handle_round_end(game_id, result))
        return True

    def _process_post_discard(self, game_id: str, events: list[ServiceEvent]) -> list[ServiceEvent]:
        """
        Process events after a discard.

        Uses the pending call prompt system: dispatches AI player responses through handlers,
        waits for player callers, or advances turn if no callers.
        """
        # check if round ended immediately (abortive draws)
        if self._check_and_handle_round_end(game_id, events):
            return events

        # Re-fetch state after potential updates
        game_state = self._games[game_id]
        round_state = game_state.round_state

        if round_state.pending_call_prompt is not None:
            # dispatch AI player call responses through handlers
            self._dispatch_ai_player_call_responses(game_id, round_state.pending_call_prompt, events)

            # Re-fetch state after AI player responses
            game_state = self._games[game_id]
            round_state = game_state.round_state

            # if player callers still pending, wait
            if round_state.pending_call_prompt is not None:
                return events

            # prompt resolved - check round end
            if self._check_and_handle_round_end(game_id, events):
                return events
        elif round_state.phase == RoundPhase.PLAYING:
            # no callers - draw for next player (turn already advanced by process_discard_phase)
            _new_round_state, new_game_state, draw_events = process_draw_phase(round_state, game_state)
            self._games[game_id] = new_game_state

            events.extend(convert_events(draw_events))

            if self._check_and_handle_round_end(game_id, events):
                return events

        return events

    def _dispatch_ai_player_call_responses(
        self,
        game_id: str,
        prompt: PendingCallPrompt,
        events: list[ServiceEvent],
    ) -> None:
        """
        Dispatch AI player responses to the pending call prompt.

        Each AI player's response goes through the same handler functions as player responses, seat by seat in order;
        resolution happens when the last caller responds. Updates stored state from each handler result. A refused
        response is a server fault (GeneratedActionError), never a silent pass.
        """
        ai_player_controller = self._ai_player_controllers[game_id]
        ai_player_seats = sorted(s for s in prompt.pending_seats if ai_player_controller.is_ai_player(s))
        for seat in ai_player_seats:
            response = ai_player_controller.get_call_response(
                seat=seat,
                round_state=self._games[game_id].round_state,
                call_type=prompt.call_type,
                tile_id=prompt.tile_id,
                caller_info=self._find_caller_info(prompt, seat),
            )
            action, data = response if response is not None else (GameAction.PASS, {})
            logger.debug("AI player call response", action=action.value, ai_seat=seat)
            result = self._dispatch_generated_action(game_id, seat=seat, action=action, data=data)
            self._update_state_from_result(game_id, result)
            events.extend(convert_events(result.events))

    def _find_caller_info(self, prompt: PendingCallPrompt, seat: int) -> int | MeldCaller:
        """
        Find caller info for a seat from the prompt's callers list.
        """
        for caller in prompt.callers:
            caller_seat = caller if isinstance(caller, int) else caller.seat
            if caller_seat == seat:
                return caller

        raise AssertionError(f"seat {seat} not found in prompt callers")

    def _handle_round_end(
        self,
        game_id: str,
        round_result: RoundResult | None = None,
    ) -> list[ServiceEvent]:
        """
        Handle the end of a round -- enter waiting state for confirmations.
        """
        frozen_game = self._games[game_id]

        if round_result is None:
            raise AssertionError("round finished but no round result found in events")

        logger.info("round ended", result_type=type(round_result).__name__)

        frozen_game = process_round_end(frozen_game, round_result)

        if check_game_end(frozen_game):
            frozen_game, game_result = finalize_game(frozen_game)
            logger.info(
                "game ended",
                winner_seat=game_result.winner_seat,
                standings=[{"seat": s.seat, "score": s.final_score} for s in game_result.standings],
            )
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
                        num_rounds=frozen_game.round_number,
                        target="all",
                    ),
                    target=BroadcastTarget(),
                ),
            ]

        # Store updated state
        self._games[game_id] = frozen_game

        # enter waiting state for round confirmation
        ai_player_controller = self._ai_player_controllers.get(game_id)
        ai_player_seats = ai_player_controller.ai_player_seats if ai_player_controller else set()
        if self._round_advance.setup_pending(game_id, ai_player_seats):
            # all AI players (no players) -- advance immediately
            return self._start_next_round(game_id)

        # return empty -- the RoundEndEvent is already in the caller's events list
        return []

    def _handle_confirm_round(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """
        Handle a player confirming readiness for the next round.
        """
        result = self._round_advance.confirm_seat(game_id, seat)
        if result is None:
            logger.warning("confirm round rejected: no round pending")
            return self._create_error_event(
                code=GameErrorCode.INVALID_ACTION,
                message="no round pending confirmation",
                target=f"seat_{seat}",
            )

        if not result:
            return []  # still waiting for other players

        # all confirmed -- start next round
        # _start_next_round already handles AI player dealer followup
        return self._start_next_round(game_id)

    def _append_furiten_changes(self, game_id: str, events: list[ServiceEvent]) -> list[ServiceEvent]:
        """
        Append furiten state-change events if round is still playing.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return events

        events.extend(self._furiten_tracker.check_changes(game_id, game_state.round_state))
        return events

    def cleanup_game(self, game_id: str) -> None:
        """
        Remove all game state for a game that was abandoned or cleaned up externally.
        """
        self._games.pop(game_id, None)
        self._ai_player_controllers.pop(game_id, None)
        self._furiten_tracker.cleanup_game(game_id)
        self._round_advance.cleanup_game(game_id)

    def replace_with_ai_player(self, game_id: str, player_name: str) -> None:
        """
        Replace a disconnected player with an AI player at their seat.
        """
        # find seat BEFORE registering AI player (_find_player_seat skips AI player seats)
        seat = self._find_player_seat(game_id, player_name)
        if seat is None:
            return

        ai_player_controller = self._ai_player_controllers.get(game_id)
        if ai_player_controller is None:
            return

        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        ai_player_controller.add_ai_player(seat, ai_player)
        logger.info("replaced player with AI", replaced_player=player_name, replaced_seat=seat)

    def restore_human_player(self, game_id: str, seat: int) -> None:
        """
        Remove the AI player at a seat and restore it for human control.
        """
        controller = self._ai_player_controllers.get(game_id)
        if controller:
            controller.remove_ai_player(seat)

    def build_reconnection_snapshot(self, game_id: str, seat: int) -> ReconnectionSnapshot | None:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return None

        round_state = game_state.round_state
        controller = self._ai_player_controllers.get(game_id)

        players_info = [
            GamePlayerInfo(
                seat=p.seat,
                name=p.name,
                is_ai_player=controller.is_ai_player(p.seat) if controller else False,
            )
            for p in round_state.players
        ]

        player_states = [
            PlayerReconnectState(
                seat=p.seat,
                score=p.score,
                discards=[
                    DiscardInfo(
                        tile_id=d.tile_id,
                        is_tsumogiri=d.is_tsumogiri,
                        is_riichi_discard=d.is_riichi_discard,
                    )
                    for d in p.discards
                ],
                melds=[frozen_meld_to_compact(m) for m in p.melds],
                is_riichi=p.is_riichi,
            )
            for p in round_state.players
        ]

        view = get_player_view(game_state, seat)
        return ReconnectionSnapshot(
            game_id=game_id,
            players=players_info,
            dealer_seat=round_state.dealer_seat,
            dealer_dice=game_state.dealer_dice,
            seat=seat,
            round_wind=view.round_wind,
            round_number=view.round_number,
            current_player_seat=round_state.current_player_seat,
            dora_indicators=view.dora_indicators,
            honba_sticks=view.honba_sticks,
            riichi_sticks=view.riichi_sticks,
            my_tiles=view.my_tiles,
            dice=view.dice,
            tiles_remaining=tiles_remaining(round_state.wall),
            player_states=player_states,
            is_furiten=is_effective_furiten(round_state.players[seat]),
        )

    def build_draw_event_for_seat(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """
        Rebuild the draw event with available actions for a specific seat.

        Right after the seat's own pon or chi it drew nothing, so there is no draw to rebuild (no draw follows a pon or
        chi on the live path either).
        """
        game_state = self._games.get(game_id)
        if game_state is None:
            return []

        round_state = game_state.round_state
        if round_state.current_player_seat != seat or round_state.is_after_meld_call:
            return []

        player = round_state.players[seat]
        if not player.tiles:
            return []

        # The last tile in hand is the drawn tile
        tile_id = player.tiles[-1]
        draw_event = create_draw_event(round_state, game_state, seat=seat, tile_id=tile_id)
        return convert_events([draw_event])

    def _auto_confirm_pending_advance(self, game_id: str, seat: int) -> list[ServiceEvent] | None:
        """
        Auto-confirm a seat's pending round advance after AI player replacement.

        Returns events if the pending advance was handled, None if not applicable.
        """
        if not self._round_advance.is_seat_required(game_id, seat):
            return None

        return self._handle_confirm_round(game_id, seat)

    def process_ai_player_actions_after_replacement(
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
        advance_events = self._auto_confirm_pending_advance(game_id, seat)
        if advance_events is not None:
            return advance_events

        round_state = game_state.round_state
        if round_state.phase != RoundPhase.PLAYING:
            return []

        events: list[ServiceEvent] = []

        # if the replaced player had a pending call prompt, resolve their response as AI player
        prompt = round_state.pending_call_prompt
        if prompt is not None and seat in prompt.pending_seats:
            self._dispatch_ai_player_call_responses(game_id, prompt, events)
            self._append_furiten_changes(game_id, events)

            # Re-fetch state after AI player responses
            game_state = self._games[game_id]
            round_state = game_state.round_state
            if round_state.pending_call_prompt is not None:
                # other player callers still pending
                return events

            # prompt fully resolved - check round end
            if self._check_and_handle_round_end(game_id, events):
                return events

        # Re-fetch state
        game_state = self._games[game_id]
        round_state = game_state.round_state

        # process AI player turns if current player is an AI player
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            ai_player_events = self._process_ai_player_followup(game_id)
            events.extend(ai_player_events)

        return events

    def _start_next_round(self, game_id: str) -> list[ServiceEvent]:
        """
        Start the next round and return events.
        """
        frozen_game = self._games[game_id]
        frozen_game = init_round(frozen_game)
        self._games[game_id] = frozen_game

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting next round", hands=hands)

        self._furiten_tracker.init_game(game_id)

        ai_player_controller = self._ai_player_controllers[game_id]

        events = self._create_round_started_events(frozen_game)

        _new_round_state, new_game_state, draw_events = process_draw_phase(
            frozen_game.round_state,
            frozen_game,
        )
        self._games[game_id] = new_game_state
        events.extend(convert_events(draw_events))

        dealer_seat = new_game_state.round_state.dealer_seat
        if ai_player_controller.is_ai_player(dealer_seat):
            ai_player_events = self._process_ai_player_followup(game_id)
            events.extend(ai_player_events)

        return events

    def _process_ai_player_followup(self, game_id: str) -> list[ServiceEvent]:
        """
        Process AI player turn actions iteratively.

        Loop until a player's turn is reached, a pending call prompt awaits player input, or the round ends. Each AI
        turn discards (or ends the round), so the loop always progresses; a refused AI action raises instead.
        """
        all_events: list[ServiceEvent] = []
        ai_player_controller = self._ai_player_controllers.get(game_id)
        if ai_player_controller is None:
            return all_events

        while (game_state := self._games.get(game_id)) is not None:
            round_state = game_state.round_state
            if round_state.phase != RoundPhase.PLAYING or round_state.pending_call_prompt is not None:
                break

            current_seat = round_state.current_player_seat
            if not ai_player_controller.is_ai_player(current_seat):
                break

            all_events.extend(self._execute_ai_player_turn(game_id, ai_player_controller, seat=current_seat))

        return all_events

    def _execute_ai_player_turn(
        self,
        game_id: str,
        ai_player_controller: AIPlayerController,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Execute a single AI player turn action; an AI that has no action or makes a refused one is a server fault.
        """
        action_data = ai_player_controller.get_turn_action(seat, self._games[game_id].round_state)
        if action_data is None:
            raise GeneratedActionError(f"AI seat {seat} returned no turn action")

        action, data = action_data
        logger.debug("AI player action", action=action.value, ai_seat=seat)
        result = self._dispatch_generated_action(game_id, seat=seat, action=action, data=data)
        return self._commit_and_process(game_id, result)
