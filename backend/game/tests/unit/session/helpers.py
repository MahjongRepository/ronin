import asyncio
from typing import TYPE_CHECKING

from mahjong.tile import TilesConverter

from game.messaging.types import SessionMessageType
from game.session.models import Game, Player, PlayerSpec
from game.session.timer import TimerConfig, TurnTimer
from game.session.timer_manager import TimerFiring
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockConnection
from game.tests.unit.helpers import _update_player, _update_round_state

if TYPE_CHECKING:
    from game.logic.enums import TimeoutType
    from game.logic.mahjong_service import MahjongGameService
    from game.session.manager import SessionManager


async def create_started_game(
    manager: SessionManager,
    *,
    game_id: str = "game1",
    player_names: list[str] | None = None,
) -> list[MockConnection]:
    player_names = player_names or ["Player0"]
    specs = []
    tickets: list[str] = []
    for i, name in enumerate(player_names):
        ticket = make_test_game_ticket(username=name, room_id=game_id, user_id=f"user-{i}")
        specs.append(PlayerSpec(name=name, user_id=f"user-{i}", game_ticket=ticket))
        tickets.append(ticket)

    manager.create_pending_game(game_id=game_id, player_specs=specs)

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


def current_wait_id(manager: SessionManager, game_id: str = "game1") -> int:
    game = manager.get_game(game_id)
    assert game is not None
    assert game.awaiting is not None
    return game.awaiting.wait_id


async def wait_for_background_tasks(manager: SessionManager) -> None:
    while manager._background_tasks:
        await asyncio.wait(set(manager._background_tasks))


def fire_turn_timer_now(manager: SessionManager, *, game_id: str, seat: int) -> asyncio.Task[None]:
    timer = manager._timer_manager.get_timer(game_id, seat)
    assert timer is not None
    configured = timer._config
    timer._config = TimerConfig(base_turn_seconds=0)
    timer._bank_seconds = 0
    manager._timer_manager.start_turn_timer(game_id, seat)
    timer._config = configured
    assert timer.task is not None
    return timer.task


def arrange_exhaustive_draw(engine: MahjongGameService, *, game_id: str) -> None:
    wall = engine._games[game_id].round_state.wall
    _update_round_state(engine, game_id, wall=wall.model_copy(update={"live_tiles": ()}))


def arrange_final_discard(engine: MahjongGameService, *, game_id: str, seat: int) -> None:
    _update_player(engine, game_id=game_id, seat=seat, score=-1000)
    arrange_exhaustive_draw(engine, game_id=game_id)


def arrange_ron_and_pon_on_a_discard(engine: MahjongGameService, *, discarder: int, ron: int, pon: int) -> int:
    four_pins = TilesConverter.string_to_136_array(pin="444")
    ittsu_waiting_on_four_pin = TilesConverter.string_to_136_array(man="123456789", pin="1123")
    pair_of_four_pin = four_pins[:2] + TilesConverter.string_to_136_array(sou="123456789", honors="12")
    discarder_hand = TilesConverter.string_to_136_array(pin="556789", honors="3456777") + four_pins[2:]
    for seat, tiles in ((ron, ittsu_waiting_on_four_pin), (pon, pair_of_four_pin), (discarder, discarder_hand)):
        _update_player(engine, game_id="game1", seat=seat, tiles=tuple(tiles))

    return four_pins[2]


def arrange_pon_now_and_on_the_next_draw(engine: MahjongGameService, *, discarder: int, caller: int) -> int:
    four_pins = TilesConverter.string_to_136_array(pin="444")
    nine_sous = TilesConverter.string_to_136_array(sou="999")
    caller_hand = (
        four_pins[:2] + nine_sous[:2] + TilesConverter.string_to_136_array(man="135", pin="79", sou="13", honors="12")
    )
    discarder_hand = TilesConverter.string_to_136_array(man="2468", pin="2356", sou="2", honors="3456") + four_pins[2:]
    _update_player(engine, game_id="game1", seat=caller, tiles=tuple(caller_hand))
    _update_player(engine, game_id="game1", seat=discarder, tiles=tuple(discarder_hand))
    wall = engine._games["game1"].round_state.wall
    live_tiles = (nine_sous[2], *(tile for tile in wall.live_tiles if tile != nine_sous[2]))
    _update_round_state(engine, "game1", wall=wall.model_copy(update={"live_tiles": live_tiles}))
    return four_pins[2]


async def run_timeout(manager: SessionManager, *, game_id: str, timeout_type: TimeoutType, seat: int) -> None:
    timer = manager._timer_manager.get_timer(game_id, seat) or TurnTimer()
    firing = TimerFiring(timer=timer, generation=timer.generation)
    await manager._handle_timeout(game_id, timeout_type, seat, firing)
