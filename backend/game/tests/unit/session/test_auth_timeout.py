from unittest.mock import patch

from game.session import manager as manager_module
from game.tests.mocks import MockConnection

from .helpers import create_started_game


class TestAuthTimeout:
    async def test_auth_timeout__when_connection_unauthenticated__should_close_and_unregister_after_timeout(
        self, manager
    ):
        conn = MockConnection()
        with patch.object(manager_module, "_AUTH_TIMEOUT_SECONDS", 0):
            manager.register_connection(conn)
            await manager._auth_timeouts[conn.connection_id]

        assert conn.is_closed
        assert conn._close_code == 4001
        # Connection must be removed from _connections to prevent a concurrent
        # join_game/reconnect from registering this closing connection.
        assert conn.connection_id not in manager._connections

    async def test_auth_timeout__when_connection_unregistered__should_cancel_timeout(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        assert conn.connection_id in manager._auth_timeouts

        manager.unregister_connection(conn)
        assert conn.connection_id not in manager._auth_timeouts

    async def test_auth_timeout__when_player_joins_game__should_cancel_timeout(self, manager):
        conns = await create_started_game(manager)
        for conn in conns:
            assert conn.connection_id not in manager._auth_timeouts

    async def test_shutdown__when_auth_timeouts_sleeping__should_cancel_them_without_closing(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        timeout_tasks = list(manager._auth_timeouts.values())
        assert len(timeout_tasks) == 2

        await manager.shutdown()
        assert len(manager._auth_timeouts) == 0
        assert all(task.cancelled() for task in timeout_tasks)
        assert not conn1.is_closed
        assert not conn2.is_closed

    async def test_auth_timeout__when_closing_raises_unexpectedly__should_log_and_close_with_1011(self, manager):
        class FirstCloseFailsConnection(MockConnection):
            def close(self, code: int = 1000, reason: str = "") -> None:
                if code == 4001:
                    raise ValueError("close failed")

                super().close(code, reason)

        conn = FirstCloseFailsConnection()
        with patch.object(manager_module, "_AUTH_TIMEOUT_SECONDS", 0):
            manager.register_connection(conn)
            await manager._auth_timeouts[conn.connection_id]

        assert conn._close_code == 1011
        assert conn._close_reason == "internal_error"

    async def test_auth_timeout__when_connection_already_removed__should_not_close(self, manager):
        conn = MockConnection()
        with patch.object(manager_module, "_AUTH_TIMEOUT_SECONDS", 0):
            manager.register_connection(conn)
            manager.unregister_connection(conn)
            await manager._auth_timeout(conn)

        # Should not close (connection is gone from registry)
        assert not conn.is_closed
