from uuid import uuid4

from game.logic.enums import WindName
from game.logic.types import GameView, PlayerView
from game.session.manager import SessionManager
from game.session.models import Game, Player
from game.tests.mocks import MockConnection


async def create_started_game(
    manager: SessionManager,
    game_id: str = "game1",
    num_bots: int = 3,
    player_names: list[str] | None = None,
) -> list[MockConnection]:
    """Create a started game through the room flow.

    Creates a room, joins players, readies them up, and returns the connections.
    The game starts automatically when all required humans are ready.
    """
    num_humans = 4 - num_bots
    if player_names is None:
        player_names = [f"Player{i}" for i in range(num_humans)]
    if len(player_names) != num_humans:
        raise ValueError(f"Expected {num_humans} player names, got {len(player_names)}")

    manager.create_room(game_id, num_bots=num_bots)
    connections: list[MockConnection] = []

    for name in player_names:
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, game_id, name, str(uuid4()))
        connections.append(conn)

    # ready up all players (last one triggers game start)
    for conn in connections:
        await manager.set_ready(conn, ready=True)

    # clear message history for clean test assertions
    for conn in connections:
        conn._outbox.clear()  # noqa: SLF001

    return connections


def make_dummy_game_view() -> GameView:
    """Create a minimal GameView for testing."""
    return GameView(
        seat=0,
        round_wind=WindName.EAST,
        round_number=1,
        dealer_seat=0,
        current_player_seat=0,
        dora_indicators=[],
        honba_sticks=0,
        riichi_sticks=0,
        my_tiles=[],
        players=[
            PlayerView(
                seat=0,
                name="Alice",
                is_bot=False,
                score=25000,
            ),
        ],
    )


def make_game_with_human(manager: SessionManager) -> tuple[Game, Player, MockConnection]:
    """Create a game with a human player who has an assigned seat."""
    conn = MockConnection()
    game = Game(game_id="game1")
    session = manager._session_store.create_session("Alice", "game1")  # noqa: SLF001
    player = Player(
        connection=conn,
        name="Alice",
        session_token=session.session_token,
        game_id="game1",
        seat=0,
    )
    game.players[conn.connection_id] = player
    manager._games["game1"] = game  # noqa: SLF001
    manager._players[conn.connection_id] = player  # noqa: SLF001
    manager._connections[conn.connection_id] = conn  # noqa: SLF001
    return game, player, conn
