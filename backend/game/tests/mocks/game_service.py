from typing import TYPE_CHECKING, cast

from game.engine import (
    NUM_PLAYERS,
    PRESET_GAME_TYPE,
    BroadcastTarget,
    Dealt,
    Decision,
    Discard,
    DrawEvent,
    GameEvent,
    GameOver,
    GamePhase,
    GameRuntime,
    GameService,
    GameStartedEvent,
    PlayerView,
    Refusal,
    RoundHeader,
    RoundStartedEvent,
    SeatTarget,
    SeatView,
    Turn,
    TurnAfterDraw,
    WindName,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.engine import Action, Awaiting, MahjongGameState, StartPosition

MOCK_RIICHI_STICK_VALUE = 1000
MOCK_STARTING_SCORE = 25000
MOCK_AWAITING = Turn(seat=0)
MOCK_GAME_OVER = GameOver()


class _MockGameState:
    __slots__ = ("seed",)

    def __init__(self, seed: str) -> None:
        self.seed = seed


class _MockRuntime(GameRuntime):
    def __init__(self, seed: str) -> None:
        super().__init__(state=cast("MahjongGameState", _MockGameState(seed=seed)))
        self.awaiting: Awaiting = Dealt()


class MockGameService(GameService):
    def __init__(self) -> None:
        self._scripted_acts: list[tuple[list[GameEvent] | Refusal, Awaiting | None]] = []

    def script_act(self, result: list[GameEvent] | Refusal, *, awaiting: Awaiting | None = None) -> None:
        self._scripted_acts.append((result, awaiting))

    def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
        mock_runtime = cast("_MockRuntime", runtime)
        if self._scripted_acts:
            result, awaiting = self._scripted_acts.pop(0)
            if not isinstance(result, Refusal):
                mock_runtime.awaiting = awaiting if awaiting is not None else Turn(seat=(seat + 1) % NUM_PLAYERS)

            return result

        mock_runtime.awaiting = Turn(seat=(seat + 1) % NUM_PLAYERS)
        return [DrawEvent(target=BroadcastTarget(), seat=seat, tile_id=getattr(action, "tile", 0), tiles_remaining=69)]

    def legal_actions(self, runtime: GameRuntime, seat: int) -> tuple[Action, ...]:
        decision = self.decision(runtime, seat)
        return decision.legal if decision is not None else ()

    def default_action(self, runtime: GameRuntime, seat: int) -> Action | None:
        decision = self.decision(runtime, seat)
        return decision.default if decision is not None else None

    def decision(self, runtime: GameRuntime, seat: int) -> Decision | None:
        if seat not in self.get_awaiting(runtime).seats:
            return None

        return Decision(
            seat=seat,
            context=TurnAfterDraw(drawn=0, rinshan=False, haitei=False),
            legal=(Discard(tile=0),),
            default=Discard(tile=0),
        )

    def new_game(
        self,
        seed: str,
        *,
        walls: Sequence[Sequence[int]] = (),
        start: StartPosition | None = None,
    ) -> tuple[GameRuntime, list[GameEvent]]:
        game_started = GameStartedEvent(
            game_type=PRESET_GAME_TYPE,
            dealer_seat=0,
            dealer_dice=((1, 1), (1, 1)),
            riichi_stick_value=MOCK_RIICHI_STICK_VALUE,
        )
        round_started = [
            RoundStartedEvent(
                seat=seat,
                round_wind=WindName.EAST,
                round_number=0,
                round_in_wind=1,
                dealer_seat=0,
                current_player_seat=0,
                dora_indicators=[],
                honba_sticks=0,
                riichi_sticks=0,
                my_tiles=[],
                players=[PlayerView(seat=i, score=MOCK_STARTING_SCORE) for i in range(NUM_PLAYERS)],
                dice=(1, 1),
                tiles_remaining=70,
                target=SeatTarget(seat=seat),
            )
            for seat in range(NUM_PLAYERS)
        ]
        return _MockRuntime(seed=seed), [game_started, *round_started]

    def begin_round(self, runtime: GameRuntime) -> list[GameEvent]:
        cast("_MockRuntime", runtime).awaiting = MOCK_AWAITING
        return []

    def deal_next_round(self, runtime: GameRuntime) -> list[GameEvent]:
        cast("_MockRuntime", runtime).awaiting = Dealt()
        return []

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        return cast("_MockRuntime", runtime).awaiting

    def view(self, runtime: GameRuntime, seat: int) -> SeatView:
        return SeatView(
            seat=seat,
            hand=(),
            drawn_tile=None,
            is_furiten=False,
            players=(),
            dora_indicators=(),
            tiles_remaining=70,
            riichi_sticks=0,
            current_player_seat=0,
            latest_discard_seat=None,
            round=RoundHeader(
                round_number=0,
                round_wind=WindName.EAST,
                round_in_wind=1,
                dealer_seat=0,
                honba_sticks=0,
                dice=(1, 1),
            ),
            result=None,
            game_phase=GamePhase.IN_PROGRESS,
            first_dealer_seat=0,
            dealer_dice=((1, 1), (1, 1)),
            round_history=(),
            decision=self.decision(runtime, seat),
        )
