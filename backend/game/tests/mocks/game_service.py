from typing import TYPE_CHECKING, Any, cast

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
from game.logic.service import Awaiting, GameService, GameStart, GameUpdate
from game.logic.settings import GameSettings, GameType
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


class _MockSettings:
    __slots__ = ("game_type",)

    def __init__(self, game_type: str = GameType.HANCHAN) -> None:
        self.game_type = game_type


class _MockRoundState:
    __slots__ = ("players",)

    def __init__(self, players: list[_MockPlayer] | None = None) -> None:
        self.players = players or []


class _MockGameState:
    __slots__ = ("rng_version", "round_number", "round_state", "settings")

    def __init__(
        self,
        rng_version: str = RNG_VERSION,
        round_state: _MockRoundState | None = None,
        settings: _MockSettings | None = None,
        round_number: int = 0,
    ) -> None:
        self.rng_version = rng_version
        self.round_state = round_state or _MockRoundState()
        self.settings = settings or _MockSettings()
        self.round_number = round_number


MOCK_AWAITING = Awaiting(kind=WaitKind.TURN, seats=frozenset(), wait_id=1, round_number=0)
MOCK_GAME_OVER = Awaiting(kind=WaitKind.NONE, seats=frozenset(), wait_id=2, round_number=0)


def mock_update(events: list[ServiceEvent], awaiting: Awaiting = MOCK_AWAITING) -> GameUpdate:
    return GameUpdate(events=events, awaiting=awaiting)


class MockGameService(GameService):
    def __init__(self) -> None:
        self._seeds: dict[str, str] = {}  # game_id -> seed
        self._all_player_names: dict[str, list[str]] = {}  # game_id -> all player names (including AI)
        self._game_types: dict[str, str] = {}  # game_id -> game_type string

    def handle_action(
        self,
        *,
        game_id: str,
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
        self._seeds[game_id] = seed if seed is not None else ""
        if settings is not None:
            self._game_types[game_id] = str(settings.game_type)

        all_names = player_names + ["AI"] * (4 - len(player_names))
        self._all_player_names[game_id] = all_names
        player_count = len(player_names)

        players = [
            GamePlayerInfo(seat=i, name=name, is_ai_player=i >= player_count) for i, name in enumerate(all_names)
        ]
        events = [
            ServiceEvent(
                data=GameStartedEvent(
                    game_id=game_id,
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
        return GameStart(events=events, awaiting=MOCK_AWAITING, seats=tuple(range(player_count)))

    def get_game_seed(self, game_id: str) -> str | None:
        return self._seeds.get(game_id)

    def get_awaiting(self, game_id: str) -> Awaiting:
        return MOCK_AWAITING

    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        if game_id not in self._seeds:
            return None

        all_names = self._all_player_names.get(game_id, [])
        players = [_MockPlayer(seat=i, name=name) for i, name in enumerate(all_names)]
        game_type = self._game_types.get(game_id, GameType.HANCHAN)
        return cast(
            "MahjongGameState",
            _MockGameState(round_state=_MockRoundState(players=players), settings=_MockSettings(game_type=game_type)),
        )

    def cleanup_game(self, game_id: str) -> None:
        self._seeds.pop(game_id, None)
        self._all_player_names.pop(game_id, None)
        self._game_types.pop(game_id, None)

    def replace_with_ai_player(self, game_id: str, seat: int) -> None:
        pass

    def restore_human_player(self, game_id: str, seat: int) -> None:
        pass

    def build_reconnection_snapshot(self, game_id: str, seat: int) -> ReconnectionSnapshot | None:
        return None

    def build_draw_event_for_seat(self, game_id: str, seat: int) -> list[ServiceEvent]:
        return []

    def process_ai_player_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> GameUpdate:
        return GameUpdate(events=[], awaiting=MOCK_AWAITING)

    def is_round_advance_pending(self, game_id: str) -> bool:
        return False

    def get_pending_round_advance_seats(self, game_id: str) -> list[int]:
        return []

    def handle_timeout(
        self,
        *,
        game_id: str,
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
