"""Tests for AuthSessionStore."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from shared.auth.session_store import AuthSessionStore


class TestCreateSession:
    def test_creates_session_with_correct_fields(self):
        store = AuthSessionStore()
        session = store.create_session("user-1", "alice")

        assert session.user_id == "user-1"
        assert session.username == "alice"
        assert session.session_id
        assert session.expires_at > session.created_at

    def test_sessions_have_unique_ids(self):
        store = AuthSessionStore()
        s1 = store.create_session("u1", "alice")
        s2 = store.create_session("u2", "bob")
        assert s1.session_id != s2.session_id


class TestGetSession:
    def test_retrieves_valid_session(self):
        store = AuthSessionStore()
        session = store.create_session("u1", "alice")

        result = store.get_session(session.session_id)
        assert result is not None
        assert result.user_id == "u1"

    def test_returns_none_for_unknown_id(self):
        store = AuthSessionStore()
        assert store.get_session("nonexistent") is None

    def test_returns_none_and_removes_expired_session(self):
        store = AuthSessionStore()
        session = store.create_session("u1", "alice", ttl_seconds=0)

        # Ensure expiry by advancing past the TTL
        with patch("shared.auth.session_store.time") as mock_time:
            mock_time.time.return_value = session.expires_at + 1
            result = store.get_session(session.session_id)

        assert result is None
        # Session should be removed from internal store
        assert session.session_id not in store._sessions


class TestDeleteSession:
    def test_removes_existing_session(self):
        store = AuthSessionStore()
        session = store.create_session("u1", "alice")

        store.delete_session(session.session_id)
        assert store.get_session(session.session_id) is None

    def test_ignores_unknown_session(self):
        store = AuthSessionStore()
        store.delete_session("nonexistent")  # should not raise


class TestCleanupExpired:
    def test_removes_expired_sessions(self):
        store = AuthSessionStore()
        store.create_session("u1", "alice", ttl_seconds=0)
        store.create_session("u2", "bob", ttl_seconds=0)
        active = store.create_session("u3", "charlie", ttl_seconds=3600)

        with patch("shared.auth.session_store.time") as mock_time:
            mock_time.time.return_value = time.time() + 1
            removed = store.cleanup_expired()

        assert removed == 2
        assert store.get_session(active.session_id) is not None

    def test_returns_zero_when_nothing_expired(self):
        store = AuthSessionStore()
        store.create_session("u1", "alice", ttl_seconds=3600)

        removed = store.cleanup_expired()
        assert removed == 0


class TestCleanupLifecycle:
    async def test_start_and_stop_cleanup(self):
        store = AuthSessionStore()
        store.start_cleanup()
        assert store._cleanup_task is not None
        assert not store._cleanup_task.done()

        await store.stop_cleanup()
        assert store._cleanup_task is None

    async def test_start_is_idempotent(self):
        store = AuthSessionStore()
        store.start_cleanup()
        task1 = store._cleanup_task

        store.start_cleanup()
        task2 = store._cleanup_task

        assert task1 is task2
        await store.stop_cleanup()

    async def test_stop_without_start_is_safe(self):
        store = AuthSessionStore()
        await store.stop_cleanup()  # should not raise

    async def test_cleanup_loop_runs_periodically(self):
        store = AuthSessionStore()
        store.create_session("u1", "alice", ttl_seconds=0)

        with patch.object(store, "cleanup_expired", wraps=store.cleanup_expired) as mock_cleanup:
            with patch("shared.auth.session_store.CLEANUP_INTERVAL_SECONDS", 0.01):
                store.start_cleanup()
                await asyncio.sleep(0.05)
                await store.stop_cleanup()

            assert mock_cleanup.call_count >= 1
