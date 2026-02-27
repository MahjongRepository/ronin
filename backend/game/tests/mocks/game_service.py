from typing import Any

from game.logic.enums import GameAction, TimeoutType, WindName
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
from game.logic.service import GameService
from game.logic.settings import GameSettings, GameType
from game.logic.types import GamePlayerInfo, PlayerView, ReconnectionSnapshot


class MockResultEvent(GameEvent):
    """Mock event for action results in tests."""

    player: str
    action: GameAction | str
    input: dict[str, Any]
    success: bool


class _MockPlayer:
    """Minimal player stub with seat and name."""

    __slots__ = ("name", "seat")

    def __init__(self, seat: int, name: str) -> None:
        self.seat = seat
        self.name = name


class _MockSettings:
    """Minimal settings stub exposing game_type."""

    __slots__ = ("game_type",)

    def __init__(self, game_type: str = GameType.HANCHAN) -> None:
        self.game_type = game_type


class _MockRoundState:
    """Minimal round state stub with players list."""

    __slots__ = ("players",)

    def __init__(self, players: list[_MockPlayer] | None = None) -> None:
        self.players = players or []


class _MockGameState:
    """Minimal game state stub for replay collection and persistence tests."""

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


class MockGameService(GameService):
    """Mock game service for testing.

    Simply echoes back actions as events.
    """

    def __init__(self) -> None:
        self._player_seats: dict[str, dict[str, int]] = {}  # game_id -> {player_name -> seat}
        self._seeds: dict[str, str] = {}  # game_id -> seed
        self._all_player_names: dict[str, list[str]] = {}  # game_id -> all player names (including AI)
        self._game_types: dict[str, str] = {}  # game_id -> game_type string

    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """Get the seat number for a player by name."""
        game_seats = self._player_seats.get(game_id)
        if game_seats is None:
            return None
        return game_seats.get(player_name)

    async def handle_action(
        self,
        game_id: str,
        player_name: str,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        event_type = EventType.DRAW
        return [
            ServiceEvent(
                event=event_type,
                data=MockResultEvent(
                    type=event_type,
                    target="all",
                    player=player_name,
                    action=action,
                    input=data,
                    success=True,
                ),
                target=BroadcastTarget(),
            ),
        ]

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> list[ServiceEvent]:
        # store player seat assignments (seat 0 for first player)
        self._player_seats[game_id] = {name: i for i, name in enumerate(player_names)}
        self._seeds[game_id] = seed if seed is not None else ""
        if settings is not None:
            self._game_types[game_id] = str(settings.game_type)

        all_names = player_names + ["AI"] * (4 - len(player_names))
        self._all_player_names[game_id] = all_names
        player_count = len(player_names)

        players = [
            GamePlayerInfo(seat=i, name=name, is_ai_player=i >= player_count) for i, name in enumerate(all_names)
        ]

        return [
            ServiceEvent(
                event=EventType.GAME_STARTED,
                data=GameStartedEvent(
                    game_id=game_id,
                    players=players,
                    dealer_seat=0,
                    dealer_dice=((1, 1), (1, 1)),
                ),
                target=BroadcastTarget(),
            ),
            ServiceEvent(
                event=EventType.ROUND_STARTED,
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
                    target="seat_0",
                ),
                target=SeatTarget(seat=0),
            ),
        ]

    def get_game_seed(self, game_id: str) -> str | None:
        """Return the seed for a game, or None if game doesn't exist."""
        return self._seeds.get(game_id)

    def get_game_state(self, game_id: str) -> _MockGameState | None:  # type: ignore[override]
        """Return a mock game state, or None if game doesn't exist."""
        if game_id not in self._seeds:
            return None
        all_names = self._all_player_names.get(game_id, [])
        players = [_MockPlayer(seat=i, name=name) for i, name in enumerate(all_names)]
        game_type = self._game_types.get(game_id, GameType.HANCHAN)
        return _MockGameState(
            round_state=_MockRoundState(players=players),
            settings=_MockSettings(game_type=game_type),
        )

    def cleanup_game(self, game_id: str) -> None:
        self._player_seats.pop(game_id, None)
        self._seeds.pop(game_id, None)
        self._all_player_names.pop(game_id, None)
        self._game_types.pop(game_id, None)

    def replace_with_ai_player(
        self,
        game_id: str,
        player_name: str,
    ) -> None:
        pass

    def restore_human_player(self, game_id: str, seat: int) -> None:
        pass

    def build_reconnection_snapshot(self, game_id: str, seat: int) -> ReconnectionSnapshot | None:
        return None

    def build_draw_event_for_seat(self, game_id: str, seat: int) -> list[ServiceEvent]:
        return []

    async def process_ai_player_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> list[ServiceEvent]:
        return []

    def is_round_advance_pending(self, game_id: str) -> bool:
        return False

    def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
        return []

    async def handle_timeout(
        self,
        game_id: str,
        player_name: str,
        timeout_type: TimeoutType,
    ) -> list[ServiceEvent]:
        event_type = EventType.DRAW
        return [
            ServiceEvent(
                event=event_type,
                data=MockResultEvent(
                    type=event_type,
                    target="all",
                    player=player_name,
                    action=f"timeout_{timeout_type.value}",
                    input={},
                    success=True,
                ),
                target=BroadcastTarget(),
            ),
        ]
