import asyncio
from unittest.mock import patch

from game.session import manager as manager_module
from game.tests.mocks import MockConnection

from .helpers import create_started_game


class TestAuthTimeout:
    async def test_auth_timeout__when_connection_unauthenticated__should_close_and_unregister_after_timeout(
        self, manager
    ):
        with patch.object(manager_module, "_AUTH_TIMEOUT_SECONDS", 0.05):
            conn = MockConnection()
            manager.register_connection(conn)
            await asyncio.sleep(0.1)

        assert conn.is_closed
        assert conn._close_code == 4001
        # Connection must be removed from _connections to prevent a concurrent
        # join_game/reconnect from registering this closing connection.
        assert conn.connection_id not in manager._connections

    async def test_auth_timeout__when_connection_authenticated__should_not_close(self, manager):
        with patch.object(manager_module, "_AUTH_TIMEOUT_SECONDS", 0.05):
            conns = await create_started_game(manager)
            await asyncio.sleep(0.1)

        assert not conns[0].is_closed

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

    async def test_auth_timeout__when_all_cancelled__should_clear_timeouts_without_closing(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        assert len(manager._auth_timeouts) == 2

        manager.cancel_all_auth_timeouts()
        assert len(manager._auth_timeouts) == 0

        await asyncio.sleep(0.01)
        assert not conn1.is_closed
        assert not conn2.is_closed

    async def test_auth_timeout__when_connection_already_removed__should_not_close(self, manager):
        conn = MockConnection()
        with patch.object(manager_module, "_AUTH_TIMEOUT_SECONDS", 0.01):
            manager.register_connection(conn)
            # Remove from connections but don't cancel the timeout
            manager._connections.pop(conn.connection_id, None)

            # Run the timeout coroutine directly
            await manager._auth_timeout(conn)

        # Should not close (connection is gone from registry)
        assert not conn.is_closed
