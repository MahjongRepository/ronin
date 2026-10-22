import asyncio
import time
from unittest.mock import AsyncMock, patch

from game.session.heartbeat import HEARTBEAT_TIMEOUT, HeartbeatMonitor
from game.session.models import Game, Player
from game.tests.mocks import MockConnection


def _resolve_once(game: Game):
    resolved: list[Game] = []

    def get_game(_game_id: str) -> Game | None:
        if resolved:
            return None

        resolved.append(game)
        return game

    return get_game


def _fail_on_loop_error(exc: Exception) -> None:
    raise AssertionError("heartbeat loop failed") from exc


class TestHeartbeatMonitorRecordConnect:
    def test_heartbeat_monitor__when_connect_recorded__should_store_last_ping(self):
        monitor = HeartbeatMonitor()
        monitor.record_connect("conn1")
        assert monitor._last_ping.get("conn1") is not None


class TestHeartbeatMonitorRecordDisconnect:
    def test_heartbeat_monitor__when_disconnect_recorded__should_remove_tracking(self):
        monitor = HeartbeatMonitor()
        monitor.record_connect("conn1")
        assert monitor._last_ping.get("conn1") is not None

        monitor.record_disconnect("conn1")
        assert monitor._last_ping.get("conn1") is None


class TestHeartbeatMonitorRecordPing:
    def test_heartbeat_monitor__when_ping_recorded__should_not_move_last_ping_backwards(self):
        monitor = HeartbeatMonitor()
        monitor.record_connect("conn1")
        initial = monitor._last_ping.get("conn1")
        assert initial is not None

        # record_ping should update the timestamp
        monitor.record_ping("conn1")
        updated = monitor._last_ping.get("conn1")
        assert updated is not None
        assert updated >= initial


class TestHeartbeatMonitorTaskManagement:
    async def test_heartbeat_monitor__when_started_for_game__should_create_task(self):
        monitor = HeartbeatMonitor()

        def get_game(_game_id):
            return None  # will cause loop to exit

        monitor.start_for_game("game1", get_game, on_error=_fail_on_loop_error)
        assert "game:game1" in monitor._tasks
        assert monitor._tasks.get("game:game1") is not None

        # clean up
        await monitor.stop_for_game("game1")

    async def test_heartbeat_monitor__when_started_twice_for_game__should_replace_and_cancel_first_task(self):
        monitor = HeartbeatMonitor()

        def get_game(_game_id):
            return None

        monitor.start_for_game("game1", get_game, on_error=_fail_on_loop_error)
        first_task = monitor._tasks.get("game:game1")
        assert first_task is not None

        # start again with the same game_id
        monitor.start_for_game("game1", get_game, on_error=_fail_on_loop_error)
        second_task = monitor._tasks.get("game:game1")
        assert second_task is not first_task

        # yield control so the cancellation propagates
        await asyncio.sleep(0)
        assert first_task.cancelled()

        # clean up
        await monitor.stop_for_game("game1")

    async def test_heartbeat_monitor__when_stopped_for_game__should_remove_task(self):
        monitor = HeartbeatMonitor()

        def get_game(_game_id):
            return None

        monitor.start_for_game("game1", get_game, on_error=_fail_on_loop_error)
        assert "game:game1" in monitor._tasks

        await monitor.stop_for_game("game1")
        assert "game1" not in monitor._tasks


class TestHeartbeatMonitorLoop:
    async def test_heartbeat_monitor__when_loop_raises__should_hand_error_to_on_error_and_end(self):
        monitor = HeartbeatMonitor()
        loop_errors: list[Exception] = []

        def get_game(_game_id):
            raise ValueError("resolver broke")

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock):
            await monitor._check_loop(
                entity_id="game1", entity_type="game", get_entity=get_game, on_error=loop_errors.append
            )

        assert [str(e) for e in loop_errors] == ["resolver broke"]

    async def test_heartbeat_monitor__when_connection_stale__should_close_with_heartbeat_timeout(self):
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)
        # set ping to past timeout
        monitor._last_ping[conn.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        game = Game(game_id="game1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        game.players[conn.connection_id] = player

        with patch("game.session.heartbeat.HEARTBEAT_CHECK_INTERVAL", 0):
            await monitor._check_loop(
                entity_id="game1", entity_type="game", get_entity=_resolve_once(game), on_error=_fail_on_loop_error
            )

        assert conn.is_closed
        assert conn._close_code == 1000
        assert conn._close_reason == "heartbeat_timeout"

    async def test_heartbeat_monitor__when_connection_fresh__should_keep_it_open(self):
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)

        game = Game(game_id="game1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        game.players[conn.connection_id] = player

        with patch("game.session.heartbeat.HEARTBEAT_CHECK_INTERVAL", 0):
            await monitor._check_loop(
                entity_id="game1", entity_type="game", get_entity=_resolve_once(game), on_error=_fail_on_loop_error
            )

        assert not conn.is_closed

    async def test_heartbeat_monitor__when_game_missing__should_exit_loop_after_one_sleep(self):
        monitor = HeartbeatMonitor()

        def get_game(_game_id):
            return None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.return_value = None
            # should exit cleanly
            await monitor._check_loop(
                entity_id="game1", entity_type="game", get_entity=get_game, on_error=_fail_on_loop_error
            )

        # verify sleep was called (loop attempted one iteration)
        mock_sleep.assert_called_once()

    async def test_heartbeat_monitor__when_one_of_two_connections_stale__should_close_only_stale_one(self):
        monitor = HeartbeatMonitor()
        conn1 = MockConnection()
        conn2 = MockConnection()
        monitor.record_connect(conn1.connection_id)
        monitor.record_connect(conn2.connection_id)
        # conn1 is stale, conn2 is fresh
        monitor._last_ping[conn1.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        game = Game(game_id="game1")
        player1 = Player(connection=conn1, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
        game.players[conn1.connection_id] = player1
        game.players[conn2.connection_id] = player2

        with patch("game.session.heartbeat.HEARTBEAT_CHECK_INTERVAL", 0):
            await monitor._check_loop(
                entity_id="game1", entity_type="game", get_entity=_resolve_once(game), on_error=_fail_on_loop_error
            )

        assert conn1.is_closed
        assert not conn2.is_closed
