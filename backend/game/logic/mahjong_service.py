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
from game.logic.decision import Action, Chi, Decision, Discard, Kan, Kyuushu, Pass, Pon, Riichi, Ron, Tsumo
from game.logic.enums import GamePhase, RoundPhase, WindName
from game.logic.events import (
    GameEndedEvent,
    GameEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
    build_call_prompt_events,
)
from game.logic.exceptions import DiscardHistoryError
from game.logic.furiten_tracker import FuritenTracker
from game.logic.game import (
    finalize_game,
    game_end_cause,
    init_game,
    init_round,
    process_round_end,
)
from game.logic.meld_compact import frozen_meld_to_compact
from game.logic.refusal import Refusal, RefusalCode, RefusalKind
from game.logic.rule_profiles import PRESET_SETTINGS
from game.logic.runtime import GameRuntime
from game.logic.service import Awaiting, Call, Dealt, GameOver, GameService, RoundOver, Turn
from game.logic.settings import NUM_PLAYERS
from game.logic.state import (
    MahjongGameState,
    MahjongRoundState,
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

    Holds no game: new_game hands each game's GameRuntime to the caller, and every later call takes it. It never learns
    who answers a seat: every call applies exactly what its caller asked for.
    """

    def new_game(
        self,
        seed: str,
        *,
        walls: Sequence[Sequence[int]] = (),
        start: StartPosition | None = None,
    ) -> tuple[GameRuntime, list[GameEvent]]:
        """
        Build a game from its seed and deal its first round.

        Returns the game's runtime and its initial events. The game plays the rules preset (PRESET_SETTINGS). The first
        rounds are dealt from walls, in order, and the rest from the seed; a start position starts the game at its table
        in place of East 1. The game stops after the deal, before the dealer's first draw (begin_round).
        """
        first_wall = list(walls[0]) if walls else None
        frozen_game = init_game(seed=seed, settings=PRESET_SETTINGS, wall=first_wall, start=start)
        runtime = GameRuntime(state=frozen_game, walls=walls)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting game", hands=hands)

        events: list[GameEvent] = [
            self._create_game_started_event(frozen_game),
            *self._create_round_started_events(frozen_game),
        ]
        runtime.first_draw_pending = True
        return runtime, events

    def begin_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
        """
        Draw the dealt round's first tile for its dealer; refuse it on any other wait.
        """
        awaiting = self.get_awaiting(runtime)
        if not isinstance(awaiting, Dealt):
            logger.info("phase call refused: no dealt round to begin", wait=type(awaiting).__name__)
            return _WRONG_PHASE

        runtime.first_draw_pending = False
        new_game_state, draw_events = process_draw_phase(runtime.state)
        runtime.commit(new_game_state)
        return list(draw_events)

    def deal_next_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
        """
        Deal the round after the one that ended, from the game's next given wall or else from its seed; refuse it on any
        other wait.
        """
        awaiting = self.get_awaiting(runtime)
        if not isinstance(awaiting, RoundOver):
            logger.info("phase call refused: no round over to deal after", wait=type(awaiting).__name__)
            return _WRONG_PHASE

        round_index = len(runtime.state.round_history)
        wall = list(runtime.walls[round_index]) if round_index < len(runtime.walls) else None
        frozen_game = init_round(runtime.state, wall=wall)
        runtime.commit(frozen_game)

        hands = {p.seat: list(p.tiles) for p in frozen_game.round_state.players}
        logger.debug("starting next round", hands=hands)

        runtime.furiten = FuritenTracker()
        runtime.first_draw_pending = True
        return [*self._create_round_started_events(frozen_game)]

    def _create_game_started_event(self, game_state: MahjongGameState) -> GameStartedEvent:
        """
        Create a single game_started event broadcast to all players.
        """
        return GameStartedEvent(
            game_type=game_state.settings.game_type,
            dealer_seat=game_state.starting_dealer_seat,
            dealer_dice=game_state.dealer_dice,
            riichi_stick_value=game_state.settings.riichi_stick_value,
        )

    def _create_round_started_events(self, game_state: MahjongGameState) -> list[RoundStartedEvent]:
        """
        Create round_started events for all players.
        """
        return [get_player_view(game_state, seat) for seat in range(NUM_PLAYERS)]

    def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
        """
        Apply one answer of one seat, or refuse it and change nothing.
        """
        logger.debug("player action", action=action)
        return self._run_action(runtime, runtime.state, seat=seat, action=action)

    def decision(self, runtime: GameRuntime, seat: int) -> Decision | None:
        """
        Return what the seat may do now, or None when the game does not await it.
        """
        if seat not in self.get_awaiting(runtime).seats:
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
        Run a seat's action; return the events, or the action's refusal.
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

        return self._commit_and_process(runtime, result)

    def _commit_and_process(self, runtime: GameRuntime, result: ActionResult) -> list[GameEvent]:
        """
        Store a handler's result and run what follows it: the round's end, when the result ended the round, then the
        furiten changes.

        Anything raised from here on comes after the commit and is a server fault.
        """
        runtime.commit(result.state)
        events = list(result.events)
        round_result = runtime.state.round_state.result
        if round_result is not None:
            events.extend(self._handle_round_end(runtime, round_result))

        events.extend(runtime.furiten.check_changes(runtime.state.round_state))
        return events

    def _dispatch_action(  # noqa: PLR0911
        self,
        game_state: MahjongGameState,
        seat: int,
        action: Action,
    ) -> ActionResult | Refusal:
        """
        Dispatch a game action to the appropriate handler: the single entry point for all action dispatch.
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

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        """
        Return what the game waits for now, naming every awaited seat.
        """
        game_state = runtime.state
        if game_state.game_phase == GamePhase.FINISHED:
            return GameOver()

        if game_state.round_state.phase == RoundPhase.FINISHED:
            return RoundOver()

        if runtime.first_draw_pending:
            return Dealt()

        prompt = game_state.round_state.pending_call_prompt
        if prompt is not None:
            return Call(seats=prompt.pending_seats)

        return Turn(seat=game_state.round_state.current_player_seat)

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

    def build_reconnection_snapshot(self, runtime: GameRuntime, seat: int) -> ReconnectionSnapshot:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.
        """
        game_state = runtime.state
        round_state = game_state.round_state
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
            game_type=game_state.settings.game_type,
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
        if seat not in self.get_awaiting(runtime).seats:
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
