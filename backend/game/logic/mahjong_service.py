from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, ValidationError

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
from game.logic.enums import GameAction, GameErrorCode, GamePhase, RoundPhase, TimeoutType, WaitKind, WindName
from game.logic.events import (
    ErrorEvent,
    GameEndedEvent,
    GameEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
    build_call_prompt_events,
)
from game.logic.exceptions import DiscardHistoryError, GeneratedActionError, InvalidGameActionError
from game.logic.furiten_tracker import FuritenTracker
from game.logic.game import (
    finalize_game,
    game_end_cause,
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
    MahjongRoundState,
    PendingCallPrompt,
    get_player_view,
    round_in_wind,
    wind_name,
)
from game.logic.state_utils import river_of
from game.logic.turn import (
    process_draw_phase,
)
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    DoubleRonResult,
    ExhaustiveDrawResult,
    GamePlayerInfo,
    KanActionData,
    NagashiManganResult,
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


@dataclass(frozen=True)
class _RoundHeader:
    """
    The header a reconnect snapshot shows its round with: the dealer, wind, round number, number within the wind and
    honba.
    """

    dealer_seat: int
    round_wind: WindName
    round_number: int
    round_in_wind: int
    honba_sticks: int


def _parse_action_data[T: BaseModel](model: type[T], *, action: GameAction, seat: int, data: dict[str, Any]) -> T:
    try:
        return model(**data)
    except ValidationError as e:
        error_types = [err["type"] for err in e.errors(include_input=False)]
        raise InvalidGameActionError(action=action.value, seat=seat, reason=f"malformed data: {error_types}") from e


def _current_round_number(game_state: MahjongGameState) -> int:
    """
    Return the number of the current round: the round in play, or the one that ended, through its advance wait.

    The round end has already advanced the round number to the next round's, so an ended round's is the one before it.
    """
    if game_state.round_state.phase == RoundPhase.FINISHED:
        return game_state.round_number - 1

    return game_state.round_number


def _snapshot_round_header(game_state: MahjongGameState) -> _RoundHeader:
    """
    Return the header of the round a reconnect snapshot shows: the round in play, or the one that ended.

    The round end has already moved the dealer, wind and honba on to the next round, so an ended round's come from its
    round history entry, taken before that advance.
    """
    round_state = game_state.round_state
    round_number = _current_round_number(game_state)
    if round_state.phase != RoundPhase.FINISHED:
        return _RoundHeader(
            dealer_seat=round_state.dealer_seat,
            round_wind=wind_name(round_state.round_wind),
            round_number=round_number,
            round_in_wind=round_in_wind(game_state),
            honba_sticks=game_state.honba_sticks,
        )

    ended = game_state.round_history[-1]
    return _RoundHeader(
        dealer_seat=ended.dealer_seat,
        round_wind=ended.round_wind,
        round_number=round_number,
        round_in_wind=ended.round_in_wind,
        honba_sticks=ended.honba_sticks,
    )


def _latest_discard_seat(round_state: MahjongRoundState) -> int | None:
    """
    Return the seat whose discard is the table's last action, else None.

    all_discards holds the round's discarded tiles in play order, so its last is the latest discard. A meld that holds
    that tile claimed it, and then no discard is the latest, never the one before it. The next seat's draw is the next
    action: the turn passes to it only on that draw, so a current seat other than the discarder means the discard is no
    longer the latest action, except after an exhaustive draw, whose turn passed to a seat the empty wall gave no tile.
    A result on the discard itself (a ron, an abort) keeps it. Raises DiscardHistoryError when that unclaimed tile lies
    last in no river.
    """
    if not round_state.all_discards:
        return None

    tile_id = round_state.all_discards[-1]
    if any(tile_id in meld.tiles for player in round_state.players for meld in player.melds):
        return None

    discarder = next((p.seat for p in round_state.players if p.discards and p.discards[-1].tile_id == tile_id), None)
    if discarder is None:
        raise DiscardHistoryError(f"the latest discard {tile_id} lies last in no river")

    wall_ran_out = isinstance(round_state.result, ExhaustiveDrawResult | NagashiManganResult)
    if discarder != round_state.current_player_seat and not wall_ran_out:
        return None

    return discarder


class MahjongGameService(GameService):
    """
    Game service for Mahjong implementing the GameService interface.

    Holds no game: start_game hands each game's GameRuntime to the caller, and every later call takes it. With
    pace_ai_turns, every call stops before an AI player's turn action and reports a WaitKind.AI_TURN wait, so the live
    session can space AI turns out in real time (advance_ai_turn plays each); without it, a call plays every AI turn it
    reaches, for the callers that want the whole game at once (the replay runner, engine tests). The game played is the
    same either way.
    """

    def __init__(self, *, pace_ai_turns: bool = False) -> None:
        self._pace_ai_turns = pace_ai_turns

    def start_game(  # noqa: PLR0913
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
        confirm_start: bool = False,
    ) -> GameStart:
        """
        Start a new mahjong game with the given players.

        Uses matchmaker to assign seats randomly and fill with AI players. Returns the game's runtime, initial state
        events for each player, the first wait and each input player's seat, in input order. When seed is provided, the
        game is deterministically reproducible. When seed is None, a random seed is generated. When wall is provided,
        use it instead of generating from seed. With confirm_start and a human seat, the game waits after the deal for
        the human seats to confirm its start (a round advance that starts the game) before the dealer draws.
        """
        game_seed = seed if seed is not None else generate_seed()

        seat_configs, player_seats = fill_seats(player_names, seed=game_seed)
        frozen_game = init_game(seat_configs, seed=game_seed, settings=settings, wall=wall)
        ai_players = {seat: AIPlayer() for seat, config in enumerate(seat_configs) if config.ai_player_type is not None}
        runtime = GameRuntime(game_id=game_id, state=frozen_game, ai=AIPlayerController(ai_players))
        call = self._begin_call(runtime)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting game", player_names=player_names, hands=hands)

        events: list[GameEvent] = [
            self._create_game_started_event(runtime),
            *self._create_round_started_events(frozen_game),
        ]

        human_seats = frozenset(range(NUM_PLAYERS)) - runtime.ai.ai_player_seats
        if confirm_start and human_seats:
            runtime.pending_confirm = PendingRoundAdvance(required_seats=human_seats, results_shown=1, starts_game=True)
        else:
            events.extend(self._draw_first_turn(runtime))

        return GameStart(runtime=runtime, events=events, awaiting=self._end_call(runtime, call), seats=player_seats)

    def _create_game_started_event(self, runtime: GameRuntime) -> GameStartedEvent:
        """
        Create a single game_started event broadcast to all players.
        """
        game_state = runtime.state
        players = [
            GamePlayerInfo(seat=p.seat, name=p.name, is_ai_player=runtime.ai.is_ai_player(p.seat))
            for p in game_state.round_state.players
        ]
        return GameStartedEvent(
            game_id=runtime.game_id,
            game_type=game_state.settings.game_type,
            players=players,
            dealer_seat=game_state.round_state.dealer_seat,
            dealer_dice=game_state.dealer_dice,
            riichi_stick_value=game_state.settings.riichi_stick_value,
        )

    def _create_round_started_events(self, game_state: MahjongGameState) -> list[RoundStartedEvent]:
        """
        Create round_started events for all players.
        """
        return [get_player_view(game_state, seat) for seat in range(NUM_PLAYERS)]

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
    ) -> list[GameEvent]:
        """
        Run a player's action and the AI players' turns it leads to; return the events.
        """
        # handle confirm_round before dispatching to game logic
        if action == GameAction.CONFIRM_ROUND:
            return self._handle_confirm_round(runtime, seat)

        # reject game actions when the round is not in progress
        if game_state.round_state.phase != RoundPhase.PLAYING or runtime.pending_confirm is not None:
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

    def _continue_with_ai_players(self, runtime: GameRuntime, events: list[GameEvent]) -> list[GameEvent]:
        """
        Run the AI players' turns after an action, when the round still plays and no call prompt waits.
        """
        round_state = runtime.state.round_state
        if round_state.phase == RoundPhase.PLAYING and round_state.pending_call_prompt is None:
            events.extend(self._process_ai_player_followup(runtime))

        return events

    def _commit_and_process(self, runtime: GameRuntime, result: ActionResult) -> list[GameEvent]:
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
                return handle_discard(
                    game_state,
                    seat=seat,
                    data=_parse_action_data(DiscardActionData, action=action, seat=seat, data=data),
                )
            case GameAction.DECLARE_RIICHI:
                return handle_riichi(
                    game_state,
                    seat=seat,
                    data=_parse_action_data(RiichiActionData, action=action, seat=seat, data=data),
                )
            case GameAction.CALL_PON:
                return handle_pon(
                    game_state, seat=seat, data=_parse_action_data(PonActionData, action=action, seat=seat, data=data)
                )
            case GameAction.CALL_CHI:
                return handle_chi(
                    game_state, seat=seat, data=_parse_action_data(ChiActionData, action=action, seat=seat, data=data)
                )
            case GameAction.CALL_KAN:
                return handle_kan(
                    game_state, seat=seat, data=_parse_action_data(KanActionData, action=action, seat=seat, data=data)
                )
            case _:  # pragma: no cover (exhaustive)
                raise AssertionError(f"action {action} has no handler")

    def _process_action_result_internal(self, runtime: GameRuntime, result: ActionResult) -> list[GameEvent]:
        """
        Run what follows a stored result, without the AI players' turns.

        The round ended: handle its end. A call prompt is pending (a discard's or a kan's): the AI seats answer it.
        """
        events = list(result.events)
        if self._check_and_handle_round_end(runtime, events):
            return events

        prompt = runtime.state.round_state.pending_call_prompt
        if prompt is not None:
            self._answer_call_prompt_for_ai_players(runtime, prompt, events)

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

        seat = game_state.round_state.current_player_seat
        return WaitKind.AI_TURN if runtime.ai.is_ai_player(seat) else WaitKind.TURN, frozenset({seat})

    @staticmethod
    def _build_awaiting(runtime: GameRuntime, *, kind: WaitKind, seats: frozenset[int]) -> Awaiting:
        """
        Build the Awaiting for a wait: its seats without the AI players' ones, and the round it belongs to.
        """
        game_state = runtime.state
        advance = runtime.pending_confirm if kind == WaitKind.ROUND_ADVANCE else None
        return Awaiting(
            kind=kind,
            seats=frozenset(s for s in seats if not runtime.ai.is_ai_player(s)),
            wait_id=game_state.wait_id,
            round_number=_current_round_number(game_state),
            results_shown=advance.results_shown if advance is not None else 1,
            starts_game=advance is not None and advance.starts_game,
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
    ) -> list[GameEvent]:
        """
        Run a timeout's default action for a seat, then the AI players' turns it leads to.
        """
        result = self._dispatch_generated_action(runtime, seat=seat, action=action, data=data)
        events = self._commit_and_process(runtime, result)
        return self._continue_with_ai_players(runtime, events)

    def _handle_turn_timeout(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
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

    def _handle_meld_timeout(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
        """
        Handle MELD timeout: pass on the call opportunity.
        """
        prompt = runtime.state.round_state.pending_call_prompt
        if prompt is None or seat not in prompt.pending_seats:
            return []

        logger.info("meld timeout, auto-passing")
        return self._run_generated_action(runtime, seat=seat, action=GameAction.PASS, data={})

    def _handle_round_advance_timeout(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
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
    ) -> list[GameEvent]:
        """
        Create an error event for a seat.
        """
        return [ErrorEvent(code=code, message=message, target=SeatTarget(seat=seat))]

    def _check_and_handle_round_end(self, runtime: GameRuntime, events: list[GameEvent]) -> bool:
        """
        Handle the round's end when the stored round carries its result; return whether it did.

        Appends the round end's own events (the game end) to events; the RoundEndEvent itself is already there. The
        result stays on the round through the round-advance wait, so finding that wait already open means the round end
        would be applied twice: a server fault.
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
        events: list[GameEvent],
    ) -> None:
        """
        Answer a pending call prompt for its AI seats, and handle the round end their answers may resolve it into.

        Human seats still pending keep the prompt open (and the round without a result).
        """
        self._dispatch_ai_player_call_responses(runtime, prompt, events)
        self._check_and_handle_round_end(runtime, events)

    def _dispatch_ai_player_call_responses(
        self,
        runtime: GameRuntime,
        prompt: PendingCallPrompt,
        events: list[GameEvent],
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
            events.extend(result.events)

    def _handle_round_end(self, runtime: GameRuntime, round_result: RoundResult) -> list[GameEvent]:
        """
        Handle the end of a round -- enter waiting state for confirmations.

        The session abandons a game whose last human leaves, so a round never ends without a human seat to confirm it.
        """
        human_seats = frozenset(range(NUM_PLAYERS)) - runtime.ai.ai_player_seats
        if not human_seats:
            raise AssertionError("round ended with no human seat")

        frozen_game = runtime.state
        logger.info("round ended", result_type=type(round_result).__name__)

        ended_round_wind = frozen_game.round_state.round_wind
        frozen_game = process_round_end(frozen_game, round_result)

        end_cause = game_end_cause(frozen_game, ended_round_wind=ended_round_wind)
        if end_cause is not None:
            frozen_game, game_result = finalize_game(frozen_game)
            logger.info(
                "game ended",
                end_cause=end_cause.value,
                winner_seat=game_result.winner_seat,
                standings=[{"seat": s.seat, "score": s.final_score} for s in game_result.standings],
            )
            runtime.commit(frozen_game)
            return [
                GameEndedEvent(
                    winner_seat=game_result.winner_seat,
                    standings=game_result.standings,
                    leftover_riichi_bonus=game_result.leftover_riichi_bonus,
                    leftover_riichi_sticks=game_result.leftover_riichi_sticks,
                    num_rounds=frozen_game.round_number,
                    end_cause=end_cause,
                ),
            ]

        # Store updated state
        runtime.commit(frozen_game)

        # enter waiting state for round confirmation
        results_shown = len(round_result.winners) if isinstance(round_result, DoubleRonResult) else 1
        runtime.pending_confirm = PendingRoundAdvance(required_seats=human_seats, results_shown=results_shown)
        # return empty -- the RoundEndEvent is already in the caller's events list
        return []

    def _handle_confirm_round(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
        """
        Handle a player confirming readiness for the next round, or for the first round's play at the game's start.

        The last confirmation deals the next round, or for the game's start lets the first round's dealer draw.
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

        runtime.pending_confirm = None
        if pending.starts_game:
            return self._draw_first_turn(runtime)

        return self._start_next_round(runtime)

    def _append_furiten_changes(self, runtime: GameRuntime, events: list[GameEvent]) -> list[GameEvent]:
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

    def restore_human_player(self, runtime: GameRuntime, seat: int) -> Awaiting:
        """
        Remove the AI player at a seat and restore it for human control; return what the game waits for now.

        An AI player's turn the seat was owed and its AI player had not played yet becomes the human's turn, a new wait
        (_end_call); any other wait is kept.
        """
        call = self._begin_call(runtime)
        runtime.ai.remove_ai_player(seat)
        return self._end_call(runtime, call)

    def advance_ai_turn(self, runtime: GameRuntime) -> GameUpdate:
        """
        Play the AI player's turn the game waits for: exactly one turn action, with the AI call responses and the round
        end it leads to; any other wait is a server fault.
        """
        call = self._begin_call(runtime)
        if call.kind != WaitKind.AI_TURN:
            raise AssertionError(f"no AI player's turn to play: the game waits for {call.kind}")

        events = self._execute_ai_player_turn(runtime, seat=call.state.round_state.current_player_seat)
        return GameUpdate(events=events, awaiting=self._end_call(runtime, call))

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
                discards=river_of(p),
                melds=[frozen_meld_to_compact(m) for m in p.melds],
                is_riichi=p.is_riichi,
                tile_count=len(p.tiles),
            )
            for p in round_state.players
        ]

        view = get_player_view(game_state, seat)
        header = _snapshot_round_header(game_state)
        return ReconnectionSnapshot(
            game_id=runtime.game_id,
            game_type=game_state.settings.game_type,
            players=players_info,
            dealer_seat=header.dealer_seat,
            first_dealer_seat=game_state.starting_dealer_seat,
            dealer_dice=game_state.dealer_dice,
            riichi_stick_value=game_state.settings.riichi_stick_value,
            seat=seat,
            round_wind=header.round_wind,
            round_number=header.round_number,
            round_in_wind=header.round_in_wind,
            current_player_seat=round_state.current_player_seat,
            latest_discard_seat=_latest_discard_seat(round_state),
            dora_indicators=view.dora_indicators,
            honba_sticks=header.honba_sticks,
            riichi_sticks=view.riichi_sticks,
            my_tiles=view.my_tiles,
            dice=view.dice,
            tiles_remaining=tiles_remaining(round_state.wall),
            player_states=player_states,
            is_furiten=runtime.furiten.is_furiten(seat),
            round_history=list(game_state.round_history),
            result=round_state.result,
        )

    def build_wait_events_for_seat(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
        """
        Rebuild the event that opened the wait the game owes the seat: its call prompt, or its turn's draw.

        A turn opens with the draw and its available actions, or right after the seat's own pon or chi, when it drew
        nothing, with the turn event, as on the live path. A round advance has no such event (the round's result is in
        the reconnect snapshot), and neither has a wait that does not await the seat.
        """
        kind, seats = self._current_wait(runtime)
        if seat not in seats:
            return []

        game_state = runtime.state
        round_state = game_state.round_state
        prompt = round_state.pending_call_prompt
        if kind == WaitKind.CALL and prompt is not None:
            return [e for e in build_call_prompt_events(prompt) if e.target == SeatTarget(seat=seat)]

        if kind != WaitKind.TURN:
            return []

        if round_state.is_after_meld_call:
            return [create_turn_event(game_state, seat=seat)]

        player = round_state.players[seat]
        if not player.tiles:
            return []

        # The last tile in hand is the drawn tile
        tile_id = player.tiles[-1]
        return [create_draw_event(game_state, seat=seat, tile_id=tile_id)]

    def _auto_confirm_pending_advance(self, runtime: GameRuntime, seat: int) -> list[GameEvent] | None:
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
    ) -> list[GameEvent]:
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

        events: list[GameEvent] = []

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

    def _start_next_round(self, runtime: GameRuntime) -> list[GameEvent]:
        """
        Start the next round and return events.
        """
        frozen_game = self._deal_next_round(runtime.state)
        runtime.commit(frozen_game)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting next round", hands=hands)

        runtime.furiten = FuritenTracker()
        return [*self._create_round_started_events(frozen_game), *self._draw_first_turn(runtime)]

    def _draw_first_turn(self, runtime: GameRuntime) -> list[GameEvent]:
        """
        Draw the dealt round's first tile for its dealer, then run the AI players' turns that follow; return the events.
        """
        new_game_state, draw_events = process_draw_phase(runtime.state)
        runtime.commit(new_game_state)
        return [*draw_events, *self._process_ai_player_followup(runtime)]

    def _deal_next_round(self, game_state: MahjongGameState) -> MahjongGameState:
        """
        Deal the round the game advanced to, from its seed.
        """
        return init_round(game_state)

    def _process_ai_player_followup(self, runtime: GameRuntime) -> list[GameEvent]:
        """
        Process AI player turn actions iteratively, unless AI turns are paced.

        Loop until a player's turn is reached, a pending call prompt awaits player input, or the round ends. Each AI
        turn discards (or ends the round), so the loop always progresses; a refused AI action raises instead. With
        paced AI turns it plays none: the game waits on the AI player's turn (WaitKind.AI_TURN) for advance_ai_turn.
        """
        if self._pace_ai_turns:
            return []

        all_events: list[GameEvent] = []
        while True:
            round_state = runtime.state.round_state
            if round_state.phase != RoundPhase.PLAYING or round_state.pending_call_prompt is not None:
                break

            current_seat = round_state.current_player_seat
            if not runtime.ai.is_ai_player(current_seat):
                break

            all_events.extend(self._execute_ai_player_turn(runtime, seat=current_seat))

        return all_events

    def _execute_ai_player_turn(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
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
