from dataclasses import dataclass
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
from game.logic.action_result import Refusal, create_draw_event, create_turn_event
from game.logic.ai_player import AIPlayer
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import GameAction, GameErrorCode, GamePhase, RoundPhase, TimeoutType, WaitKind
from game.logic.events import (
    ErrorEvent,
    GameEndedEvent,
    GameStartedEvent,
    SeatTarget,
    ServiceEvent,
    convert_events,
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
from game.logic.round_advance import PendingRoundAdvance
from game.logic.runtime import GameRuntime
from game.logic.service import Awaiting, GameService, GameStart, GameUpdate
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
    DoubleRonResult,
    GamePlayerInfo,
    KanActionData,
    PlayerReconnectState,
    PonActionData,
    ReconnectionSnapshot,
    RiichiActionData,
    RoundResult,
)
from game.logic.wall import tiles_remaining

if TYPE_CHECKING:
    from game.logic.action_result import ActionResult
    from game.logic.settings import GameSettings

logger = structlog.get_logger()


@dataclass(frozen=True)
class _CallStart:
    """
    The game as an engine call found it: its state and the wait in progress, with the AI players' seats included.
    """

    state: MahjongGameState
    kind: WaitKind
    seats: frozenset[int]


class MahjongGameService(GameService):
    """
    Game service for Mahjong implementing the GameService interface.

    Holds no game: start_game hands each game's GameRuntime to the caller, and every later call takes it.
    """

    def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> GameStart:
        """
        Start a new mahjong game with the given players.

        Uses matchmaker to assign seats randomly and fill with AI players. Returns the game's runtime, initial state
        events for each player, the first wait and each input player's seat, in input order. When seed is provided, the
        game is deterministically reproducible. When seed is None, a random seed is generated. When wall is provided,
        use it instead of generating from seed.
        """
        game_seed = seed if seed is not None else generate_seed()

        seat_configs, player_seats = fill_seats(player_names, seed=game_seed)
        frozen_game = init_game(seat_configs, seed=game_seed, settings=settings, wall=wall)
        ai_players = {seat: AIPlayer() for seat, config in enumerate(seat_configs) if config.ai_player_type is not None}
        runtime = GameRuntime(game_id=game_id, state=frozen_game, ai=AIPlayerController(ai_players))
        call = self._begin_call(runtime)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting game", player_names=player_names, hands=hands)

        events = [self._create_game_started_event(runtime), *self._create_round_started_events(frozen_game)]

        new_game_state, draw_events = process_draw_phase(frozen_game)
        runtime.commit(new_game_state)
        events.extend(convert_events(draw_events))

        # process AI player turns if dealer is an AI player
        if runtime.ai.is_ai_player(new_game_state.round_state.dealer_seat):
            events.extend(self._process_ai_player_followup(runtime))

        return GameStart(runtime=runtime, events=events, awaiting=self._end_call(runtime, call), seats=player_seats)

    def _create_game_started_event(self, runtime: GameRuntime) -> ServiceEvent:
        """
        Create a single game_started event broadcast to all players.
        """
        game_state = runtime.state
        players = [
            GamePlayerInfo(seat=p.seat, name=p.name, is_ai_player=runtime.ai.is_ai_player(p.seat))
            for p in game_state.round_state.players
        ]
        return ServiceEvent(
            data=GameStartedEvent(
                game_id=runtime.game_id,
                game_type=game_state.settings.game_type,
                players=players,
                dealer_seat=game_state.round_state.dealer_seat,
                dealer_dice=game_state.dealer_dice,
            ),
        )

    def _create_round_started_events(self, game_state: MahjongGameState) -> list[ServiceEvent]:
        """
        Create round_started events for all players.
        """
        return [ServiceEvent(data=get_player_view(game_state, seat)) for seat in range(NUM_PLAYERS)]

    def handle_action(
        self,
        runtime: GameRuntime,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> GameUpdate:
        """
        Handle a game action from the player at a seat.

        Processes the action and triggers AI player turns as needed. An action for an AI player's seat is a server
        fault.
        """
        call = self._begin_call(runtime)
        self._require_human_seat(runtime, seat)
        logger.debug("player action", action=action, action_data=data)
        events = self._run_action(runtime, call.state, seat=seat, action=action, data=data)
        return GameUpdate(events=events, awaiting=self._end_call(runtime, call))

    def _run_action(
        self,
        runtime: GameRuntime,
        game_state: MahjongGameState,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Run a player's action and the AI players' turns it leads to; return the events.
        """
        # handle confirm_round before dispatching to game logic
        if action == GameAction.CONFIRM_ROUND:
            return self._handle_confirm_round(runtime, seat)

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
                seat=seat,
            )

        result = self._dispatch_action(game_state, seat=seat, action=action, data=data)
        if isinstance(result, Refusal):
            return self._create_error_event(code=result.code, message=result.message, seat=seat)

        events = self._commit_and_process(runtime, result)
        return self._continue_with_ai_players(runtime, events)

    def _continue_with_ai_players(self, runtime: GameRuntime, events: list[ServiceEvent]) -> list[ServiceEvent]:
        """
        Run the AI players' turns after an action, when the round still plays and no call prompt waits.
        """
        round_state = runtime.state.round_state
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            events.extend(self._process_ai_player_followup(runtime))

        return events

    def _commit_and_process(self, runtime: GameRuntime, result: ActionResult) -> list[ServiceEvent]:
        """
        Store a handler's result and run what follows it (_process_action_result_internal).

        Does NOT trigger AI player turns, to avoid recursion: the top-level caller runs them. Anything raised from here
        on comes after the commit and is a server fault.
        """
        runtime.commit(result.state)
        events = self._process_action_result_internal(runtime, result)
        return self._append_furiten_changes(runtime, events)

    def _dispatch_generated_action(
        self,
        runtime: GameRuntime,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> ActionResult:
        """
        Dispatch an action the server made for a seat: an AI decision or a timeout default.

        The server generated it, so a refusal, structural or soft, is a server fault: raise GeneratedActionError, never
        kick the seat or count the refusal as progress.
        """
        try:
            result = self._dispatch_action(runtime.state, seat=seat, action=action, data=data)
        except InvalidGameActionError as e:
            raise GeneratedActionError(f"seat {seat} {action.value} refused: {e.reason}") from e

        if isinstance(result, Refusal):
            raise GeneratedActionError(f"seat {seat} {action.value} refused: {result.code.value}: {result.message}")

        return result

    def _dispatch_action(  # noqa: PLR0911
        self,
        game_state: MahjongGameState,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> ActionResult | Refusal:
        """
        Dispatch a game action to the appropriate handler.

        Single entry point for all action dispatch: player actions, AI decisions and timeout defaults.
        CONFIRM_ROUND is handled separately by the round confirmation path.
        """
        match action:
            # No-data actions
            case GameAction.DECLARE_TSUMO:
                return handle_tsumo(game_state, seat=seat)
            case GameAction.CALL_RON:
                return handle_ron(game_state, seat=seat)
            case GameAction.CALL_KYUUSHU:
                return handle_kyuushu(game_state, seat=seat)
            case GameAction.PASS:
                return handle_pass(game_state, seat=seat)
            # Data actions
            case GameAction.DISCARD:
                return handle_discard(game_state, seat=seat, data=DiscardActionData(**data))
            case GameAction.DECLARE_RIICHI:
                return handle_riichi(game_state, seat=seat, data=RiichiActionData(**data))
            case GameAction.CALL_PON:
                return handle_pon(game_state, seat=seat, data=PonActionData(**data))
            case GameAction.CALL_CHI:
                return handle_chi(game_state, seat=seat, data=ChiActionData(**data))
            case GameAction.CALL_KAN:
                return handle_kan(game_state, seat=seat, data=KanActionData(**data))
            case _:  # pragma: no cover (exhaustive)
                raise AssertionError(f"action {action} has no handler")

    def _process_action_result_internal(self, runtime: GameRuntime, result: ActionResult) -> list[ServiceEvent]:
        """
        Run what follows a stored result, without the AI players' turns.

        The round ended: handle its end. A call prompt is pending (a discard's or a kan's): the AI seats answer it.
        Otherwise a discard nobody can call leads to the next player's draw.
        """
        events = convert_events(result.events)
        if self._check_and_handle_round_end(runtime, events):
            return events

        prompt = runtime.state.round_state.pending_call_prompt
        if prompt is not None:
            self._answer_call_prompt_for_ai_players(runtime, prompt, events)
        elif result.needs_post_discard:
            self._draw_after_discard(runtime, events)

        return events

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        """
        Return what a running game waits for now, with the seats as the AI players hold them at this moment.
        """
        kind, seats = self._current_wait(runtime)
        return self._build_awaiting(runtime, kind=kind, seats=seats)

    def _begin_call(self, runtime: GameRuntime) -> _CallStart:
        """
        Capture the game's state and wait before an engine call that may change them.
        """
        kind, seats = self._current_wait(runtime)
        return _CallStart(state=runtime.state, kind=kind, seats=seats)

    @staticmethod
    def _require_human_seat(runtime: GameRuntime, seat: int) -> None:
        """
        Refuse a call on behalf of a seat an AI player controls: the session only ever acts for a connected human.
        """
        if runtime.ai.is_ai_player(seat):
            raise AssertionError(f"seat {seat} is controlled by an AI player")

    def _end_call(self, runtime: GameRuntime, call: _CallStart) -> Awaiting:
        """
        Return what the game waits for after a call, bumping the wait id when the call ended the wait it began in.

        The call kept its wait when that wait is of the same kind and either lost seats (a partial prompt response or
        confirmation, or an AI player answering for a replaced seat) or, with the same seats, left the state untouched
        (an error result, a timeout or replacement with nothing to do). Same seats on a changed state is a new wait: the
        turn came back to the same seat, or a kan's replacement draw.
        """
        kind, seats = self._current_wait(runtime)
        kept = kind == call.kind and (seats < call.seats or (seats == call.seats and runtime.state is call.state))
        if not kept:
            runtime.commit(runtime.state.model_copy(update={"wait_id": call.state.wait_id + 1}))

        return self._build_awaiting(runtime, kind=kind, seats=seats)

    @staticmethod
    def _current_wait(runtime: GameRuntime) -> tuple[WaitKind, frozenset[int]]:
        """
        Return the kind of the game's current wait and every seat it waits on, AI players included.
        """
        game_state = runtime.state
        if game_state.game_phase == GamePhase.FINISHED:
            return WaitKind.NONE, frozenset()

        if runtime.pending_confirm is not None:
            return WaitKind.ROUND_ADVANCE, runtime.pending_confirm.unconfirmed_seats

        prompt = game_state.round_state.pending_call_prompt
        if prompt is not None:
            return WaitKind.CALL, prompt.pending_seats

        return WaitKind.TURN, frozenset({game_state.round_state.current_player_seat})

    @staticmethod
    def _build_awaiting(runtime: GameRuntime, *, kind: WaitKind, seats: frozenset[int]) -> Awaiting:
        """
        Build the Awaiting for a wait: its seats without the AI players' ones, and the round it belongs to.
        """
        game_state = runtime.state
        round_over = game_state.round_state.phase == RoundPhase.FINISHED
        pending = runtime.pending_confirm
        return Awaiting(
            kind=kind,
            seats=frozenset(s for s in seats if not runtime.ai.is_ai_player(s)),
            wait_id=game_state.wait_id,
            round_number=game_state.round_number - 1 if round_over else game_state.round_number,
            results_shown=pending.results_shown if kind == WaitKind.ROUND_ADVANCE and pending is not None else 1,
        )

    def handle_timeout(
        self,
        runtime: GameRuntime,
        *,
        seat: int,
        timeout_type: TimeoutType,
    ) -> GameUpdate:
        """
        Handle a player timeout by performing the default action.

        For TURN timeout: the default discard (the drawn tile unless kuikae forbids it).
        For MELD timeout: pass on the call opportunity.
        For ROUND_ADVANCE timeout: auto-confirm round advancement.
        A timeout for an AI player's seat is a server fault.
        """
        call = self._begin_call(runtime)
        self._require_human_seat(runtime, seat)
        match timeout_type:
            case TimeoutType.TURN:
                events = self._handle_turn_timeout(runtime, seat)
            case TimeoutType.MELD:
                events = self._handle_meld_timeout(runtime, seat)
            case TimeoutType.ROUND_ADVANCE:
                events = self._handle_round_advance_timeout(runtime, seat)
            case _:  # pragma: no cover (exhaustive)
                raise AssertionError(f"unknown timeout type: {timeout_type}")

        return GameUpdate(events=events, awaiting=self._end_call(runtime, call))

    def _run_generated_action(
        self,
        runtime: GameRuntime,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Run a timeout's default action for a seat, then the AI players' turns it leads to.
        """
        result = self._dispatch_generated_action(runtime, seat=seat, action=action, data=data)
        events = self._commit_and_process(runtime, result)
        return self._continue_with_ai_players(runtime, events)

    def _handle_turn_timeout(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        """
        Handle TURN timeout: make the default discard (choose_default_discard).
        """
        round_state = runtime.state.round_state
        if round_state.phase != RoundPhase.PLAYING or round_state.current_player_seat != seat:
            logger.debug("turn timeout ignored: not the seat's turn")
            return []

        if round_state.pending_call_prompt is not None:
            logger.debug("turn timeout ignored: call prompt pending")
            return []

        tile_id = choose_default_discard(round_state.players[seat])
        logger.info("turn timeout, auto-discarding", tile_id=tile_id)
        return self._run_generated_action(runtime, seat=seat, action=GameAction.DISCARD, data={"tile_id": tile_id})

    def _handle_meld_timeout(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        """
        Handle MELD timeout: pass on the call opportunity.
        """
        prompt = runtime.state.round_state.pending_call_prompt
        if prompt is None or seat not in prompt.pending_seats:
            return []

        logger.info("meld timeout, auto-passing")
        return self._run_generated_action(runtime, seat=seat, action=GameAction.PASS, data={})

    def _handle_round_advance_timeout(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        """
        Handle ROUND_ADVANCE timeout: confirm the round end for the seat.

        The timer runs only while the seat's confirmation is pending, so finding none is a server fault.
        """
        if runtime.pending_confirm is None:
            raise GeneratedActionError(f"round advance timeout for seat {seat} with no round pending confirmation")

        return self._handle_confirm_round(runtime, seat)

    def _create_error_event(
        self,
        code: GameErrorCode,
        message: str,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Create an error event for a seat, wrapped in a ServiceEvent.
        """
        return [ServiceEvent(data=ErrorEvent(code=code, message=message, target=SeatTarget(seat=seat)))]

    def _check_and_handle_round_end(self, runtime: GameRuntime, events: list[ServiceEvent]) -> bool:
        """
        Handle the round's end when the stored round carries its result; return whether it did.

        Appends the round end's own events (game end, or the next round when no human has to confirm) to events; the
        RoundEndEvent itself is already there. The result stays on the round through the round-advance wait, so finding
        that wait already open means the round end would be applied twice: a server fault.
        """
        result = runtime.state.round_state.result
        if result is None:
            return False

        if runtime.pending_confirm is not None:
            raise AssertionError("round end already handled: its round advance is pending")

        events.extend(self._handle_round_end(runtime, result))
        return True

    def _answer_call_prompt_for_ai_players(
        self,
        runtime: GameRuntime,
        prompt: PendingCallPrompt,
        events: list[ServiceEvent],
    ) -> None:
        """
        Answer a pending call prompt for its AI seats, and handle the round end their answers may resolve it into.

        Human seats still pending keep the prompt open (and the round without a result).
        """
        self._dispatch_ai_player_call_responses(runtime, prompt, events)
        self._check_and_handle_round_end(runtime, events)

    def _draw_after_discard(self, runtime: GameRuntime, events: list[ServiceEvent]) -> None:
        """
        Draw for the next player after a discard nobody can call (process_discard_phase already advanced the turn).
        """
        new_game_state, draw_events = process_draw_phase(runtime.state)
        runtime.commit(new_game_state)
        events.extend(convert_events(draw_events))
        self._check_and_handle_round_end(runtime, events)

    def _dispatch_ai_player_call_responses(
        self,
        runtime: GameRuntime,
        prompt: PendingCallPrompt,
        events: list[ServiceEvent],
    ) -> None:
        """
        Dispatch AI player responses to the pending call prompt.

        Each AI player's response goes through the same handler functions as player responses, seat by seat in order;
        resolution happens when the last caller responds. Updates stored state from each handler result. A refused
        response is a server fault (GeneratedActionError), never a silent pass.
        """
        ai_player_seats = sorted(s for s in prompt.pending_seats if runtime.ai.is_ai_player(s))
        for seat in ai_player_seats:
            response = runtime.ai.get_call_response(
                round_state=runtime.state.round_state,
                tile_id=prompt.tile_id,
                caller=prompt.caller(seat),
            )
            action, data = response if response is not None else (GameAction.PASS, {})
            logger.debug("AI player call response", action=action.value, ai_seat=seat)
            result = self._dispatch_generated_action(runtime, seat=seat, action=action, data=data)
            runtime.commit(result.state)
            events.extend(convert_events(result.events))

    def _handle_round_end(self, runtime: GameRuntime, round_result: RoundResult) -> list[ServiceEvent]:
        """
        Handle the end of a round -- enter waiting state for confirmations.
        """
        frozen_game = runtime.state
        logger.info("round ended", result_type=type(round_result).__name__)

        frozen_game = process_round_end(frozen_game, round_result)

        if check_game_end(frozen_game):
            frozen_game, game_result = finalize_game(frozen_game)
            logger.info(
                "game ended",
                winner_seat=game_result.winner_seat,
                standings=[{"seat": s.seat, "score": s.final_score} for s in game_result.standings],
            )
            runtime.commit(frozen_game)
            return [
                ServiceEvent(
                    data=GameEndedEvent(
                        winner_seat=game_result.winner_seat,
                        standings=game_result.standings,
                        leftover_riichi_bonus=game_result.leftover_riichi_bonus,
                        num_rounds=frozen_game.round_number,
                    ),
                ),
            ]

        # Store updated state
        runtime.commit(frozen_game)

        # enter waiting state for round confirmation
        human_seats = frozenset(range(NUM_PLAYERS)) - runtime.ai.ai_player_seats
        if not human_seats:
            return self._start_next_round(runtime)

        results_shown = len(round_result.winners) if isinstance(round_result, DoubleRonResult) else 1
        runtime.pending_confirm = PendingRoundAdvance(required_seats=human_seats, results_shown=results_shown)
        # return empty -- the RoundEndEvent is already in the caller's events list
        return []

    def _handle_confirm_round(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        """
        Handle a player confirming readiness for the next round.
        """
        pending = runtime.pending_confirm
        if pending is None:
            logger.warning("confirm round rejected: no round pending")
            return self._create_error_event(
                code=GameErrorCode.INVALID_ACTION,
                message="no round pending confirmation",
                seat=seat,
            )

        if not pending.confirm(seat):
            return []  # still waiting for other players

        # all confirmed -- start next round
        # _start_next_round already handles AI player dealer followup
        runtime.pending_confirm = None
        return self._start_next_round(runtime)

    def _append_furiten_changes(self, runtime: GameRuntime, events: list[ServiceEvent]) -> list[ServiceEvent]:
        """
        Append furiten state-change events if round is still playing.
        """
        events.extend(runtime.furiten.check_changes(runtime.state.round_state))
        return events

    def replace_with_ai_player(self, runtime: GameRuntime, seat: int) -> None:
        """
        Replace a disconnected player with an AI player at their seat.
        """
        runtime.ai.add_ai_player(seat, AIPlayer())
        logger.info("replaced player with AI", replaced_seat=seat)

    def restore_human_player(self, runtime: GameRuntime, seat: int) -> None:
        """
        Remove the AI player at a seat and restore it for human control.
        """
        runtime.ai.remove_ai_player(seat)

    def build_reconnection_snapshot(self, runtime: GameRuntime, seat: int) -> ReconnectionSnapshot:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.
        """
        game_state = runtime.state
        round_state = game_state.round_state
        players_info = [
            GamePlayerInfo(seat=p.seat, name=p.name, is_ai_player=runtime.ai.is_ai_player(p.seat))
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
            game_id=runtime.game_id,
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
            is_furiten=runtime.furiten.is_furiten(seat),
            round_history=list(game_state.round_history),
        )

    def build_turn_event_for_seat(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        """
        Rebuild the event that opened the seat's turn: its draw with its available actions, or the turn event.

        Right after the seat's own pon or chi it drew nothing: its turn opened with the turn event, as on the live path.
        """
        game_state = runtime.state
        round_state = game_state.round_state
        if round_state.current_player_seat != seat:
            return []

        if round_state.is_after_meld_call:
            return convert_events([create_turn_event(game_state, seat=seat)])

        player = round_state.players[seat]
        if not player.tiles:
            return []

        # The last tile in hand is the drawn tile
        tile_id = player.tiles[-1]
        draw_event = create_draw_event(game_state, seat=seat, tile_id=tile_id)
        return convert_events([draw_event])

    def _auto_confirm_pending_advance(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent] | None:
        """
        Auto-confirm a seat's pending round advance after AI player replacement.

        Returns events if the pending advance was handled, None if not applicable.
        """
        pending = runtime.pending_confirm
        if pending is None or seat not in pending.required_seats:
            return None

        return self._handle_confirm_round(runtime, seat)

    def process_ai_player_actions_after_replacement(
        self,
        runtime: GameRuntime,
        seat: int,
    ) -> GameUpdate:
        """
        Process pending AI player actions after a player was replaced with an AI player at the given seat.
        """
        call = self._begin_call(runtime)
        events = self._run_ai_player_actions_after_replacement(runtime, call.state, seat=seat)
        return GameUpdate(events=events, awaiting=self._end_call(runtime, call))

    def _run_ai_player_actions_after_replacement(
        self,
        runtime: GameRuntime,
        game_state: MahjongGameState,
        *,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Resolve the replaced seat's pending round confirmation or call response as an AI player, then run the AI turns.
        """
        # if there's a pending round advance, auto-confirm for the replaced player
        advance_events = self._auto_confirm_pending_advance(runtime, seat)
        if advance_events is not None:
            return advance_events

        round_state = game_state.round_state
        if round_state.phase != RoundPhase.PLAYING:
            return []

        events: list[ServiceEvent] = []

        # if the replaced player had a pending call prompt, resolve their response as AI player
        prompt = round_state.pending_call_prompt
        if prompt is not None and seat in prompt.pending_seats:
            self._dispatch_ai_player_call_responses(runtime, prompt, events)
            self._append_furiten_changes(runtime, events)

            # Re-fetch state after AI player responses
            game_state = runtime.state
            round_state = game_state.round_state
            if round_state.pending_call_prompt is not None:
                # other player callers still pending
                return events

            # prompt fully resolved - check round end
            if self._check_and_handle_round_end(runtime, events):
                return events

        # Re-fetch state
        game_state = runtime.state
        round_state = game_state.round_state

        # process AI player turns if current player is an AI player
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            ai_player_events = self._process_ai_player_followup(runtime)
            events.extend(ai_player_events)

        return events

    def _start_next_round(self, runtime: GameRuntime) -> list[ServiceEvent]:
        """
        Start the next round and return events.
        """
        frozen_game = runtime.state
        frozen_game = init_round(frozen_game)
        runtime.commit(frozen_game)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting next round", hands=hands)

        runtime.furiten = FuritenTracker()
        events = self._create_round_started_events(frozen_game)

        new_game_state, draw_events = process_draw_phase(frozen_game)
        runtime.commit(new_game_state)
        events.extend(convert_events(draw_events))

        if runtime.ai.is_ai_player(new_game_state.round_state.dealer_seat):
            events.extend(self._process_ai_player_followup(runtime))

        return events

    def _process_ai_player_followup(self, runtime: GameRuntime) -> list[ServiceEvent]:
        """
        Process AI player turn actions iteratively.

        Loop until a player's turn is reached, a pending call prompt awaits player input, or the round ends. Each AI
        turn discards (or ends the round), so the loop always progresses; a refused AI action raises instead.
        """
        all_events: list[ServiceEvent] = []
        while True:
            round_state = runtime.state.round_state
            if round_state.phase != RoundPhase.PLAYING or round_state.pending_call_prompt is not None:
                break

            current_seat = round_state.current_player_seat
            if not runtime.ai.is_ai_player(current_seat):
                break

            all_events.extend(self._execute_ai_player_turn(runtime, seat=current_seat))

        return all_events

    def _execute_ai_player_turn(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        """
        Execute a single AI player turn action; an AI that has no action or makes a refused one is a server fault.
        """
        action_data = runtime.ai.get_turn_action(seat, runtime.state.round_state)
        if action_data is None:
            raise GeneratedActionError(f"AI seat {seat} returned no turn action")

        action, data = action_data
        logger.debug("AI player action", action=action.value, ai_seat=seat)
        result = self._dispatch_generated_action(runtime, seat=seat, action=action, data=data)
        return self._commit_and_process(runtime, result)
