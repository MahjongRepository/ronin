from dataclasses import dataclass
from typing import TYPE_CHECKING

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
from game.logic.action_result import create_draw_event, create_turn_event
from game.logic.actions import build_decision
from game.logic.ai_player import AIPlayer
from game.logic.ai_player_controller import AIPlayerController
from game.logic.decision import Action, Chi, Decision, Discard, Kan, Kyuushu, Pass, Pon, Riichi, Ron, Tsumo
from game.logic.enums import GamePhase, RoundPhase, WaitKind, WindName
from game.logic.events import (
    GameEndedEvent,
    GameEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
    build_call_prompt_events,
)
from game.logic.exceptions import DiscardHistoryError, GeneratedActionError
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
from game.logic.refusal import Refusal, RefusalCode, RefusalKind
from game.logic.rng import generate_seed
from game.logic.rule_profiles import PRESET_SETTINGS
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
    ExhaustiveDrawResult,
    GamePlayerInfo,
    NagashiManganResult,
    PlayerReconnectState,
    ReconnectionSnapshot,
    RoundResult,
    StartPosition,
)
from game.logic.wall import tiles_remaining

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.logic.action_result import ActionResult

logger = structlog.get_logger()

_WRONG_PHASE = Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.WRONG_PHASE)


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


def _current_round_number(game_state: MahjongGameState) -> int:
    """
    Return the number of the current round: the round in play, or the one that ended, while the game waits on its end.

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

    def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        walls: Sequence[Sequence[int]] = (),
        start: StartPosition | None = None,
    ) -> GameStart:
        """
        Start a new mahjong game with the given players.

        Uses matchmaker to assign seats randomly and fill with AI players. Returns the game's runtime, initial state
        events for each player, the first wait and each input player's seat, in input order. When seed is provided, the
        game is deterministically reproducible. When seed is None, a random seed is generated. The game plays the rules
        preset (PRESET_SETTINGS). The first rounds are dealt from walls, in order, and the rest from the seed; a start
        position starts the game at its table in place of East 1. The game stops after the deal, before the dealer's
        first draw (begin_round).
        """
        game_seed = seed if seed is not None else generate_seed()

        seat_configs, player_seats = fill_seats(player_names, seed=game_seed)
        first_wall = list(walls[0]) if walls else None
        frozen_game = init_game(seat_configs, seed=game_seed, settings=PRESET_SETTINGS, wall=first_wall, start=start)
        ai_players = {seat: AIPlayer() for seat, config in enumerate(seat_configs) if config.ai_player_type is not None}
        runtime = GameRuntime(game_id=game_id, state=frozen_game, ai=AIPlayerController(ai_players), walls=walls)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting game", player_names=player_names, hands=hands)

        events: list[GameEvent] = [
            self._create_game_started_event(runtime),
            *self._create_round_started_events(frozen_game),
        ]
        runtime.first_draw_pending = True
        return GameStart(runtime=runtime, events=events, awaiting=self.get_awaiting(runtime), seats=player_seats)

    def begin_round(self, runtime: GameRuntime) -> GameUpdate | Refusal:
        """
        Draw the dealt round's first tile for its dealer, with the AI turns that follow it; refuse it on any other wait.
        """
        kind, _ = self._current_wait(runtime)
        if kind != WaitKind.DEALT:
            logger.info("phase call refused: no dealt round to begin", wait=kind.value)
            return _WRONG_PHASE

        runtime.first_draw_pending = False
        events = self._draw_first_turn(runtime)
        return GameUpdate(events=events, awaiting=self.get_awaiting(runtime))

    def deal_next_round(self, runtime: GameRuntime) -> GameUpdate | Refusal:
        """
        Deal the round after the one that ended, from the game's next given wall or else from its seed; refuse it on any
        other wait.
        """
        kind, _ = self._current_wait(runtime)
        if kind != WaitKind.ROUND_OVER:
            logger.info("phase call refused: no round over to deal after", wait=kind.value)
            return _WRONG_PHASE

        round_index = len(runtime.state.round_history)
        wall = list(runtime.walls[round_index]) if round_index < len(runtime.walls) else None
        frozen_game = init_round(runtime.state, wall=wall)
        runtime.commit(frozen_game)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting next round", hands=hands)

        runtime.furiten = FuritenTracker()
        runtime.first_draw_pending = True
        events: list[GameEvent] = [*self._create_round_started_events(frozen_game)]
        return GameUpdate(events=events, awaiting=self.get_awaiting(runtime))

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
            dealer_seat=game_state.starting_dealer_seat,
            dealer_dice=game_state.dealer_dice,
            riichi_stick_value=game_state.settings.riichi_stick_value,
        )

    def _create_round_started_events(self, game_state: MahjongGameState) -> list[RoundStartedEvent]:
        """
        Create round_started events for all players.
        """
        return [get_player_view(game_state, seat) for seat in range(NUM_PLAYERS)]

    def act(self, runtime: GameRuntime, seat: int, action: Action) -> GameUpdate | Refusal:
        """
        Apply one action of the player at a seat, or refuse it and change nothing.

        Processes the action and triggers AI player turns as needed. An action for an AI player's seat is a server
        fault.
        """
        self._require_human_seat(runtime, seat)
        logger.debug("player action", action=action)
        events = self._run_action(runtime, runtime.state, seat=seat, action=action)
        if isinstance(events, Refusal):
            return events

        return GameUpdate(events=events, awaiting=self.get_awaiting(runtime))

    def decision(self, runtime: GameRuntime, seat: int) -> Decision | None:
        """
        Return what the seat may do now, or None when the game does not await it; an AI player's seat on its turn is
        awaited here, though Awaiting leaves it out.
        """
        _, seats = self._current_wait(runtime)
        if seat not in seats:
            return None

        return build_decision(runtime.state, seat)

    def legal_actions(self, runtime: GameRuntime, seat: int) -> tuple[Action, ...]:
        """
        Return every action the seat may take now; none when the game does not await it.
        """
        decision = self.decision(runtime, seat)
        return decision.legal if decision is not None else ()

    def default_action(self, runtime: GameRuntime, seat: int) -> Action | None:
        """
        Return the action a timeout takes for the seat, never a win or a call; None when the game does not await it.
        """
        decision = self.decision(runtime, seat)
        return decision.default if decision is not None else None

    def _run_action(
        self,
        runtime: GameRuntime,
        game_state: MahjongGameState,
        *,
        seat: int,
        action: Action,
    ) -> list[GameEvent] | Refusal:
        """
        Run a player's action and the AI players' turns it leads to; return the events, or the action's refusal.
        """
        if game_state.round_state.phase != RoundPhase.PLAYING or runtime.first_draw_pending:
            logger.warning(
                "action rejected: round not in progress",
                phase=game_state.round_state.phase.value,
                action=action,
            )
            return _WRONG_PHASE

        result = self._dispatch_action(game_state, seat=seat, action=action)
        if isinstance(result, Refusal):
            return result

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

    def _dispatch_generated_action(self, runtime: GameRuntime, *, seat: int, action: Action) -> ActionResult:
        """
        Dispatch an action the engine made for an AI player's seat.

        The engine generated it, so a refusal of any kind is a server fault: raise GeneratedActionError, never kick the
        seat or count the refusal as progress.
        """
        result = self._dispatch_action(runtime.state, seat=seat, action=action)
        if isinstance(result, Refusal):
            raise GeneratedActionError(f"seat {seat} {action} refused: {result.kind.value}: {result.code.value}")

        return result

    def _dispatch_action(  # noqa: PLR0911
        self,
        game_state: MahjongGameState,
        seat: int,
        action: Action,
    ) -> ActionResult | Refusal:
        """
        Dispatch a game action to the appropriate handler.

        Single entry point for all action dispatch: player actions and AI decisions.
        """
        match action:
            case Discard():
                return handle_discard(game_state, seat=seat, action=action)
            case Riichi():
                return handle_riichi(game_state, seat=seat, action=action)
            case Tsumo():
                return handle_tsumo(game_state, seat=seat)
            case Ron():
                return handle_ron(game_state, seat=seat)
            case Kyuushu():
                return handle_kyuushu(game_state, seat=seat)
            case Pass():
                return handle_pass(game_state, seat=seat)
            case Pon():
                return handle_pon(game_state, seat=seat)
            case Chi():
                return handle_chi(game_state, seat=seat, action=action)
            case Kan():
                return handle_kan(game_state, seat=seat, action=action)
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

    @staticmethod
    def _require_human_seat(runtime: GameRuntime, seat: int) -> None:
        """
        Refuse a call on behalf of a seat an AI player controls: the session only ever acts for a connected human.
        """
        if runtime.ai.is_ai_player(seat):
            raise AssertionError(f"seat {seat} is controlled by an AI player")

    @staticmethod
    def _current_wait(runtime: GameRuntime) -> tuple[WaitKind, frozenset[int]]:
        """
        Return the kind of the game's current wait and every seat it waits on, AI players included.
        """
        game_state = runtime.state
        if game_state.game_phase == GamePhase.FINISHED:
            return WaitKind.NONE, frozenset()

        if game_state.round_state.phase == RoundPhase.FINISHED:
            return WaitKind.ROUND_OVER, frozenset()

        if runtime.first_draw_pending:
            return WaitKind.DEALT, frozenset()

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
        return Awaiting(
            kind=kind,
            seats=frozenset(s for s in seats if not runtime.ai.is_ai_player(s)),
            round_number=_current_round_number(runtime.state),
        )

    def _check_and_handle_round_end(self, runtime: GameRuntime, events: list[GameEvent]) -> bool:
        """
        Handle the round's end when the stored round carries its result; return whether it did.

        Appends the round end's own events (the game end) to events; the RoundEndEvent itself is already there.
        """
        result = runtime.state.round_state.result
        if result is None:
            return False

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
            action = response if response is not None else Pass()
            logger.debug("AI player call response", action=action, ai_seat=seat)
            result = self._dispatch_generated_action(runtime, seat=seat, action=action)
            runtime.commit(result.state)
            events.extend(result.events)

    def _handle_round_end(self, runtime: GameRuntime, round_result: RoundResult) -> list[GameEvent]:
        """
        Handle the end of a round: settle it, then end the game or stop until the caller deals the next round.
        """
        frozen_game = runtime.state
        logger.info("round ended", result_type=type(round_result).__name__)

        ended_round = frozen_game.round_state
        frozen_game = process_round_end(frozen_game, round_result)

        end_cause = game_end_cause(
            frozen_game,
            ended_round_wind=ended_round.round_wind,
            ended_dealer_seat=ended_round.dealer_seat,
        )
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

        runtime.commit(frozen_game)
        return []

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

        An AI player's turn the seat was owed and its AI player had not played yet becomes the human's turn.
        """
        runtime.ai.remove_ai_player(seat)
        return self.get_awaiting(runtime)

    def advance_ai_turn(self, runtime: GameRuntime) -> GameUpdate:
        """
        Play the AI player's turn the game waits for: exactly one turn action, with the AI call responses and the round
        end it leads to; any other wait is a server fault.
        """
        kind, _ = self._current_wait(runtime)
        if kind != WaitKind.AI_TURN:
            raise AssertionError(f"no AI player's turn to play: the game waits for {kind}")

        events = self._execute_ai_player_turn(runtime, seat=runtime.state.round_state.current_player_seat)
        return GameUpdate(events=events, awaiting=self.get_awaiting(runtime))

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
        nothing, with the turn event, as on the live path. A wait that does not await the seat has no such event.
        """
        _, seats = self._current_wait(runtime)
        if seat not in seats:
            return []

        game_state = runtime.state
        round_state = game_state.round_state
        prompt = round_state.pending_call_prompt
        if prompt is not None:
            return [e for e in build_call_prompt_events(prompt) if e.target == SeatTarget(seat=seat)]

        if round_state.is_after_meld_call:
            return [create_turn_event(game_state, seat=seat)]

        player = round_state.players[seat]
        if not player.tiles:
            return []

        # The last tile in hand is the drawn tile
        tile_id = player.tiles[-1]
        return [create_draw_event(game_state, seat=seat, tile_id=tile_id)]

    def process_ai_player_actions_after_replacement(
        self,
        runtime: GameRuntime,
        seat: int,
    ) -> GameUpdate:
        """
        Process pending AI player actions after a player was replaced with an AI player at the given seat.
        """
        events = self._run_ai_player_actions_after_replacement(runtime, runtime.state, seat=seat)
        return GameUpdate(events=events, awaiting=self.get_awaiting(runtime))

    def _run_ai_player_actions_after_replacement(
        self,
        runtime: GameRuntime,
        game_state: MahjongGameState,
        *,
        seat: int,
    ) -> list[GameEvent]:
        """
        Resolve the replaced seat's pending call response as an AI player, then run the AI turns; nothing while the
        round is not in play.
        """
        round_state = game_state.round_state
        if round_state.phase != RoundPhase.PLAYING or runtime.first_draw_pending:
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

    def _draw_first_turn(self, runtime: GameRuntime) -> list[GameEvent]:
        """
        Draw the dealt round's first tile for its dealer, then run the AI players' turns that follow; return the events.
        """
        new_game_state, draw_events = process_draw_phase(runtime.state)
        runtime.commit(new_game_state)
        return [*draw_events, *self._process_ai_player_followup(runtime)]

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
        action = runtime.ai.get_turn_action(seat, runtime.state.round_state)
        if action is None:
            raise GeneratedActionError(f"AI seat {seat} returned no turn action")

        logger.debug("AI player action", action=action, ai_seat=seat)
        result = self._dispatch_generated_action(runtime, seat=seat, action=action)
        return self._commit_and_process(runtime, result)
