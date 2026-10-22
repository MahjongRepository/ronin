from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from shared.auth.session_store import AuthSessionStore
from shared.dal.models import AccountType


class TestCreateSession:
    def test_session_store_create_session__when_called__should_set_fields_and_future_expiry(self):
        store = AuthSessionStore()
        session = store.create_session(user_id="user-1", username="alice")
        assert session.user_id == "user-1"
        assert session.username == "alice"
        assert session.session_id
        assert session.expires_at > session.created_at

    def test_session_store_create_session__when_no_account_type__should_default_to_human(self):
        store = AuthSessionStore()
        session = store.create_session(user_id="user-1", username="alice")
        assert session.account_type == AccountType.HUMAN

    def test_session_store_create_session__when_bot__should_store_bot_account_type(self):
        store = AuthSessionStore()
        session = store.create_session(user_id="bot-1", username="TestBot", account_type=AccountType.BOT)
        assert session.account_type == AccountType.BOT

    def test_session_store_create_session__when_bot_session_fetched__should_keep_account_type(self):
        store = AuthSessionStore()
        session = store.create_session(user_id="bot-1", username="TestBot", account_type=AccountType.BOT)

        result = store.get_session(session.session_id)
        assert result is not None
        assert result.account_type == AccountType.BOT


class TestGetSession:
    def test_session_store_get_session__when_valid__should_return_session(self):
        store = AuthSessionStore()
        session = store.create_session(user_id="u1", username="alice")

        result = store.get_session(session.session_id)
        assert result is not None
        assert result.user_id == "u1"

    def test_session_store_get_session__when_unknown_id__should_return_none(self):
        store = AuthSessionStore()
        assert store.get_session("nonexistent") is None

    def test_session_store_get_session__when_expired__should_return_none_and_remove_it(self):
        store = AuthSessionStore()
        session = store.create_session(user_id="u1", username="alice", ttl_seconds=0)

        # Ensure expiry by advancing past the TTL
        with patch("shared.auth.session_store.time") as mock_time:
            mock_time.time.return_value = session.expires_at + 1
            result = store.get_session(session.session_id)

        assert result is None
        # Session should be removed from internal store
        assert session.session_id not in store._sessions


class TestDeleteSession:
    def test_session_store_delete_session__when_existing__should_remove_it(self):
        store = AuthSessionStore()
        session = store.create_session(user_id="u1", username="alice")

        store.delete_session(session.session_id)
        assert store.get_session(session.session_id) is None

    def test_session_store_delete_session__when_unknown__should_not_raise(self):
        store = AuthSessionStore()
        store.delete_session("nonexistent")  # should not raise


class TestCleanupExpired:
    def test_session_store_cleanup_expired__when_some_expired__should_remove_only_expired(self):
        store = AuthSessionStore()
        store.create_session(user_id="u1", username="alice", ttl_seconds=0)
        store.create_session(user_id="u2", username="bob", ttl_seconds=0)
        active = store.create_session(user_id="u3", username="charlie", ttl_seconds=3600)

        with patch("shared.auth.session_store.time") as mock_time:
            mock_time.time.return_value = time.time() + 1
            removed = store.cleanup_expired()

        assert removed == 2
        assert store.get_session(active.session_id) is not None

    def test_session_store_cleanup_expired__when_none_expired__should_return_zero(self):
        store = AuthSessionStore()
        store.create_session(user_id="u1", username="alice", ttl_seconds=3600)

        removed = store.cleanup_expired()
        assert removed == 0


class TestCleanupLifecycle:
    async def test_session_store_cleanup__when_started_and_stopped__should_manage_task(self):
        store = AuthSessionStore()
        store.start_cleanup()
        assert store._cleanup_task is not None
        assert not store._cleanup_task.done()

        await store.stop_cleanup()
        assert store._cleanup_task is None

    async def test_session_store_cleanup__when_started_twice__should_keep_same_task(self):
        store = AuthSessionStore()
        store.start_cleanup()
        task1 = store._cleanup_task

        store.start_cleanup()
        task2 = store._cleanup_task
        assert task1 is task2

        await store.stop_cleanup()

    async def test_session_store_cleanup__when_stopped_without_start__should_not_raise(self):
        store = AuthSessionStore()
        await store.stop_cleanup()  # should not raise

    async def test_session_store_cleanup__when_running__should_call_cleanup_periodically(self):
        store = AuthSessionStore()
        store.create_session(user_id="u1", username="alice", ttl_seconds=0)

        with (
            patch.object(store, "cleanup_expired", wraps=store.cleanup_expired) as mock_cleanup,
            patch(
                "shared.auth.session_store.asyncio.sleep",
                new_callable=AsyncMock,
                side_effect=[None, None, asyncio.CancelledError()],
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await store._cleanup_loop()

        assert mock_cleanup.call_count == 2

    async def test_session_store_cleanup__when_a_tick_raises__should_log_and_keep_cleaning(self, caplog):
        store = AuthSessionStore()

        with (
            patch.object(store, "cleanup_expired", side_effect=[RuntimeError("tick failed"), 0]) as mock_cleanup,
            patch(
                "shared.auth.session_store.asyncio.sleep",
                new_callable=AsyncMock,
                side_effect=[None, None, asyncio.CancelledError()],
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await store._cleanup_loop()

        assert mock_cleanup.call_count == 2
        assert "session cleanup tick failed" in caplog.text
