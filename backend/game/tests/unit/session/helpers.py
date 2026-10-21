from typing import TYPE_CHECKING

from game.logic.enums import WindName
from game.logic.settings import NUM_PLAYERS
from game.logic.types import GameView, PlayerView
from game.messaging.types import SessionMessageType
from game.session.models import Game, Player, PlayerSpec
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockConnection

if TYPE_CHECKING:
    from game.session.manager import SessionManager


async def create_started_game(
    manager: SessionManager,
    *,
    game_id: str = "game1",
    num_ai_players: int = 3,
    player_names: list[str] | None = None,
) -> list[MockConnection]:
    num_players = NUM_PLAYERS - num_ai_players
    if player_names is None:
        player_names = [f"Player{i}" for i in range(num_players)]

    if len(player_names) != num_players:
        raise ValueError(f"Expected {num_players} player names, got {len(player_names)}")

    specs = []
    tickets: list[str] = []
    for i, name in enumerate(player_names):
        ticket = make_test_game_ticket(username=name, room_id=game_id, user_id=f"user-{i}")
        specs.append(PlayerSpec(name=name, user_id=f"user-{i}", game_ticket=ticket))
        tickets.append(ticket)

    manager.create_pending_game(game_id=game_id, player_specs=specs, num_ai_players=num_ai_players)

    connections: list[MockConnection] = []
    for i, _name in enumerate(player_names):
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, game_id=game_id, session_token=tickets[i])
        connections.append(conn)

    # clear message history for clean test assertions
    for conn in connections:
        conn._outbox.clear()

    return connections


def make_dummy_game_view() -> GameView:
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
                score=25000,
            ),
        ],
    )


def make_game_with_player(manager: SessionManager) -> tuple[Game, Player, MockConnection]:
    conn = MockConnection()
    game = Game(game_id="game1")
    session = manager._session_store.create_session(player_name="Alice", game_id="game1")
    player = Player(
        connection=conn,
        name="Alice",
        session_token=session.session_token,
        game_id="game1",
        seat=0,
    )
    game.players[conn.connection_id] = player

    manager._games["game1"] = game
    manager._players[conn.connection_id] = player
    manager._connections[conn.connection_id] = conn
    return game, player, conn


async def disconnect_and_reconnect(
    manager: SessionManager,
    conn: MockConnection,
    game_id: str = "game1",
) -> tuple[MockConnection, str]:
    player = manager._players[conn.connection_id]
    token = player.session_token
    await manager.leave_game(conn, notify_player=False)

    new_conn = MockConnection()
    manager.register_connection(new_conn)
    await manager.reconnect(new_conn, game_id=game_id, session_token=token)
    reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
    assert len(reconnect_msgs) == 1, f"Expected 1 game_reconnected message, got {len(reconnect_msgs)}"

    return new_conn, token
