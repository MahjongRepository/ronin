from typing import TYPE_CHECKING, Any, cast

from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import GameAction, TimeoutType, WaitKind, WindName
from game.logic.events import (
    BroadcastTarget,
    EventType,
    GameEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.rng import RNG_VERSION
from game.logic.runtime import GameRuntime
from game.logic.service import Awaiting, GameService, GameStart, GameUpdate
from game.logic.settings import GameSettings
from game.logic.types import GamePlayerInfo, PlayerView, ReconnectionSnapshot

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


class MockResultEvent(GameEvent):
    seat: int
    action: GameAction | str
    input: dict[str, Any]
    success: bool


class _MockPlayer:
    __slots__ = ("name", "seat")

    def __init__(self, seat: int, name: str) -> None:
        self.seat = seat
        self.name = name


class _MockRoundState:
    __slots__ = ("players",)

    def __init__(self, players: list[_MockPlayer] | None = None) -> None:
        self.players = players or []


class _MockGameState:
    __slots__ = ("rng_version", "round_number", "round_state", "seed", "settings")

    def __init__(
        self,
        seed: str = "",
        rng_version: str = RNG_VERSION,
        round_state: _MockRoundState | None = None,
        settings: GameSettings | None = None,
        round_number: int = 0,
    ) -> None:
        self.seed = seed
        self.rng_version = rng_version
        self.round_state = round_state or _MockRoundState()
        self.settings = settings or GameSettings()
        self.round_number = round_number


MOCK_AWAITING = Awaiting(kind=WaitKind.TURN, seats=frozenset(), wait_id=1, round_number=0)
MOCK_GAME_OVER = Awaiting(kind=WaitKind.NONE, seats=frozenset(), wait_id=2, round_number=0)


def mock_update(events: list[ServiceEvent], awaiting: Awaiting = MOCK_AWAITING) -> GameUpdate:
    return GameUpdate(events=events, awaiting=awaiting)


class MockGameService(GameService):
    def handle_action(
        self,
        runtime: GameRuntime,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> GameUpdate:
        event = MockResultEvent(
            type=EventType.DRAW,
            target=BroadcastTarget(),
            seat=seat,
            action=action,
            input=data,
            success=True,
        )
        return GameUpdate(events=[ServiceEvent(data=event)], awaiting=MOCK_AWAITING)

    def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> GameStart:
        all_names = player_names + ["AI"] * (4 - len(player_names))
        player_count = len(player_names)
        state = _MockGameState(
            seed=seed if seed is not None else "",
            round_state=_MockRoundState(players=[_MockPlayer(seat=i, name=name) for i, name in enumerate(all_names)]),
            settings=settings,
        )
        runtime = GameRuntime(game_id=game_id, state=cast("MahjongGameState", state), ai=AIPlayerController({}))

        players = [
            GamePlayerInfo(seat=i, name=name, is_ai_player=i >= player_count) for i, name in enumerate(all_names)
        ]
        events = [
            ServiceEvent(
                data=GameStartedEvent(
                    game_id=game_id,
                    game_type=state.settings.game_type,
                    players=players,
                    dealer_seat=0,
                    dealer_dice=((1, 1), (1, 1)),
                ),
            ),
            ServiceEvent(
                data=RoundStartedEvent(
                    seat=0,
                    round_wind=WindName.EAST,
                    round_number=0,
                    dealer_seat=0,
                    current_player_seat=0,
                    dora_indicators=[],
                    honba_sticks=0,
                    riichi_sticks=0,
                    my_tiles=[],
                    players=[PlayerView(seat=i, score=25000) for i in range(4)],
                    target=SeatTarget(seat=0),
                ),
            ),
        ]
        return GameStart(runtime=runtime, events=events, awaiting=MOCK_AWAITING, seats=tuple(range(player_count)))

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        return MOCK_AWAITING

    def replace_with_ai_player(self, runtime: GameRuntime, seat: int) -> None:
        pass

    def restore_human_player(self, runtime: GameRuntime, seat: int) -> None:
        pass

    def build_reconnection_snapshot(self, runtime: GameRuntime, seat: int) -> ReconnectionSnapshot:
        return ReconnectionSnapshot(
            game_id=runtime.game_id,
            players=[
                GamePlayerInfo(seat=p.seat, name=p.name, is_ai_player=False) for p in runtime.state.round_state.players
            ],
            dealer_seat=0,
            dealer_dice=((1, 1), (1, 1)),
            seat=seat,
            round_wind=WindName.EAST,
            round_number=0,
            current_player_seat=0,
            dora_indicators=[],
            honba_sticks=0,
            riichi_sticks=0,
            my_tiles=[],
            dice=(1, 1),
            tiles_remaining=70,
            player_states=[],
            is_furiten=False,
            round_history=[],
        )

    def build_wait_events_for_seat(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        return []

    def process_ai_player_actions_after_replacement(
        self,
        runtime: GameRuntime,
        seat: int,
    ) -> GameUpdate:
        return GameUpdate(events=[], awaiting=MOCK_AWAITING)

    def handle_timeout(
        self,
        runtime: GameRuntime,
        *,
        seat: int,
        timeout_type: TimeoutType,
    ) -> GameUpdate:
        event = MockResultEvent(
            type=EventType.DRAW,
            target=BroadcastTarget(),
            seat=seat,
            action=f"timeout_{timeout_type.value}",
            input={},
            success=True,
        )
        return GameUpdate(events=[ServiceEvent(data=event)], awaiting=MOCK_AWAITING)
