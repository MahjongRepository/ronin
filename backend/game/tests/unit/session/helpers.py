import asyncio
from typing import TYPE_CHECKING

from mahjong.tile import TilesConverter

from game.messaging.types import SessionMessageType
from game.session.models import PlayerSpec
from game.session.timer import TimerConfig
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockConnection
from game.tests.unit.helpers import _update_player, _update_round_state

if TYPE_CHECKING:
    from game.logic.enums import TimeoutType
    from game.logic.runtime import GameRuntime
    from game.session.manager import SessionManager
    from game.session.models import GameSession, Participant

ENGINE_SEED = (
    "04a42c07b15b2cdfc5e518f3fe2d8fb0060412714f1d1a09558079cb875c0348b642e5faea6ceb315dc5ae346feca87c"
    "a53baeb9ce574ae287e6dd2eb4c692b4c88fa6c1ca09eb3da03d5405da300f22c2ff88ce02c50097a7ee70b988c0e25b"
)


def participant_of(manager: SessionManager, conn: MockConnection) -> Participant:
    return manager._bound[conn.connection_id]


def game_of(manager: SessionManager, game_id: str = "game1") -> GameSession:
    game = manager.get_game(game_id)
    assert game is not None
    return game


def runtime_of(manager: SessionManager, game_id: str = "game1") -> GameRuntime:
    runtime = game_of(manager, game_id).runtime
    assert runtime is not None
    return runtime


def create_started_game(
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
        manager.join_game(conn, game_id=game_id, session_token=tickets[i])
        connections.append(conn)

    # clear message history for clean test assertions
    for conn in connections:
        conn._outbox.clear()

    return connections


def disconnect_and_reconnect(
    manager: SessionManager,
    conn: MockConnection,
    game_id: str = "game1",
) -> tuple[MockConnection, str]:
    token = participant_of(manager, conn).ticket
    manager.leave_game(conn, notify_player=False)

    new_conn = MockConnection()
    manager.register_connection(new_conn)
    manager.reconnect(new_conn, game_id=game_id, session_token=token)
    reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
    assert len(reconnect_msgs) == 1, f"Expected 1 game_reconnected message, got {len(reconnect_msgs)}"

    return new_conn, token


def current_wait_id(manager: SessionManager, game_id: str = "game1") -> int:
    game = game_of(manager, game_id)
    assert game.awaiting is not None
    return game.awaiting.wait_id


async def wait_for_background_tasks(manager: SessionManager) -> None:
    while manager._background_tasks:
        await asyncio.wait(set(manager._background_tasks))


def fire_turn_timer_now(manager: SessionManager, *, game_id: str, seat: int) -> asyncio.Task[None]:
    participant = game_of(manager, game_id).at_seat(seat)
    assert participant is not None
    timer = participant.timer
    configured = timer._config
    timer._config = TimerConfig(base_turn_seconds=0)
    timer._bank_seconds = 0
    manager._start_turn_timer(participant)
    timer._config = configured
    assert timer.task is not None
    return timer.task


def arrange_exhaustive_draw(runtime: GameRuntime) -> None:
    wall = runtime.state.round_state.wall
    _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))


def arrange_final_discard(runtime: GameRuntime, *, seat: int) -> None:
    _update_player(runtime, seat=seat, score=-1000)
    arrange_exhaustive_draw(runtime)


def arrange_ron_and_pon_on_a_discard(runtime: GameRuntime, *, discarder: int, ron: int, pon: int) -> int:
    four_pins = TilesConverter.string_to_136_array(pin="444")
    ittsu_waiting_on_four_pin = TilesConverter.string_to_136_array(man="123456789", pin="1123")
    pair_of_four_pin = four_pins[:2] + TilesConverter.string_to_136_array(sou="123456789", honors="12")
    discarder_hand = TilesConverter.string_to_136_array(pin="556789", honors="3456777") + four_pins[2:]
    for seat, tiles in ((ron, ittsu_waiting_on_four_pin), (pon, pair_of_four_pin), (discarder, discarder_hand)):
        _update_player(runtime, seat=seat, tiles=tuple(tiles))

    return four_pins[2]


def arrange_pon_now_and_on_the_next_draw(runtime: GameRuntime, *, discarder: int, caller: int) -> int:
    four_pins = TilesConverter.string_to_136_array(pin="444")
    nine_sous = TilesConverter.string_to_136_array(sou="999")
    caller_hand = (
        four_pins[:2] + nine_sous[:2] + TilesConverter.string_to_136_array(man="135", pin="79", sou="13", honors="12")
    )
    discarder_hand = TilesConverter.string_to_136_array(man="2468", pin="2356", sou="2", honors="3456") + four_pins[2:]
    _update_player(runtime, seat=caller, tiles=tuple(caller_hand))
    _update_player(runtime, seat=discarder, tiles=tuple(discarder_hand))
    wall = runtime.state.round_state.wall
    live_tiles = (nine_sous[2], *(tile for tile in wall.live_tiles if tile != nine_sous[2]))
    _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": live_tiles}))
    return four_pins[2]


def run_timeout(manager: SessionManager, *, game_id: str, timeout_type: TimeoutType, seat: int) -> None:
    participant = game_of(manager, game_id).at_seat(seat)
    assert participant is not None
    manager._handle_timeout(participant, timeout_type)
