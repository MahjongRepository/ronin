"""Unit tests for MatchmakingManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lobby.matchmaking.manager import MatchmakingManager
from lobby.matchmaking.models import MATCHMAKING_SEATS, QueueEntry


def _make_entry(user_id: str = "u1", username: str = "alice", connection_id: str = "c1") -> QueueEntry:
    return QueueEntry(
        connection_id=connection_id,
        user_id=user_id,
        username=username,
        websocket=MagicMock(),
    )


class TestAddPlayer:
    def test_add_increments_queue_size(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry())
        assert mgr.queue_size == 1

    def test_duplicate_user_raises(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1"))
        with pytest.raises(ValueError, match="already_in_queue"):
            mgr.add_player(_make_entry(user_id="u1", connection_id="c2"))

    def test_different_users_allowed(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1"))
        mgr.add_player(_make_entry(user_id="u2", connection_id="c2"))
        assert mgr.queue_size == 2


class TestRemovePlayer:
    def test_remove_decrements_queue_size(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(connection_id="c1"))
        mgr.remove_player("c1")
        assert mgr.queue_size == 0

    def test_remove_nonexistent_is_noop(self):
        mgr = MatchmakingManager()
        mgr.remove_player("nonexistent")
        assert mgr.queue_size == 0

    def test_remove_allows_same_user_to_rejoin(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1"))
        mgr.remove_player("c1")
        mgr.add_player(_make_entry(user_id="u1", connection_id="c2"))
        assert mgr.queue_size == 1


class TestTryMatch:
    def test_returns_none_when_not_enough_players(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS - 1):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        assert mgr.try_match() is None

    def test_returns_matched_players_when_enough(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        matched = mgr.try_match()
        assert matched is not None
        assert len(matched) == MATCHMAKING_SEATS
        assert mgr.queue_size == 0

    def test_remaining_players_stay_in_queue(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS + 2):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        matched = mgr.try_match()
        assert matched is not None
        assert len(matched) == MATCHMAKING_SEATS
        assert mgr.queue_size == 2

    def test_matched_players_move_to_in_flight(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        mgr.try_match()
        # Matched players are in-flight, not in queue, but still tracked
        assert mgr.has_user("u0")
        assert mgr.has_user("u1")
        assert mgr.queue_size == 0

    def test_in_flight_players_cannot_rejoin(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        mgr.try_match()
        with pytest.raises(ValueError, match="already_in_queue"):
            mgr.add_player(_make_entry(user_id="u0", connection_id="c_new"))

    def test_clear_in_flight_allows_rejoin(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        mgr.try_match()
        mgr.clear_in_flight({"u0", "u1", "u2", "u3"})
        assert not mgr.has_user("u0")
        mgr.add_player(_make_entry(user_id="u0", connection_id="c_new"))
        assert mgr.has_user("u0")


class TestRequeueAtFront:
    def test_requeued_players_appear_at_front(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1", username="first"))
        entry = _make_entry(user_id="u0", connection_id="c0", username="requeued")
        mgr.requeue_at_front([entry])
        assert mgr.queue_size == 2
        # Fill the remaining seats to trigger a match and verify ordering
        for i in range(2, MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        matched = mgr.try_match()
        assert matched is not None
        assert matched[0].username == "requeued"

    def test_requeue_skips_already_present_users(self):
        mgr = MatchmakingManager()
        entry = _make_entry(user_id="u1", connection_id="c1")
        mgr.add_player(entry)
        mgr.requeue_at_front([entry])
        assert mgr.queue_size == 1

    def test_requeue_clears_in_flight(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))
        matched = mgr.try_match()
        assert matched is not None
        # Requeue some entries -- they move from in_flight back to queue
        mgr.requeue_at_front(matched[:2])
        assert mgr.has_user("u0")  # requeued -> in _user_ids
        assert mgr.has_user("u1")  # requeued -> in _user_ids
        assert mgr.has_user("u2")  # still in _in_flight
        assert mgr.has_user("u3")  # still in _in_flight
        assert mgr.queue_size == 2


class TestHasUser:
    def test_returns_true_for_queued_user(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1"))
        assert mgr.has_user("u1") is True

    def test_returns_false_for_absent_user(self):
        mgr = MatchmakingManager()
        assert mgr.has_user("u1") is False
