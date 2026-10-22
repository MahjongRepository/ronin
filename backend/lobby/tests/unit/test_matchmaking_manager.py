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
    def test_matchmaking_queue_add__should_increment_queue_size(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry())
        assert mgr.queue_size == 1

    def test_matchmaking_queue_add__when_occupancy_reports_a_conflict__should_raise_it_before_queueing(self):
        mgr = MatchmakingManager(find_conflict=lambda user_id: "already_in_room" if user_id == "u1" else None)
        with pytest.raises(ValueError, match="already_in_room"):
            mgr.add_player(_make_entry(user_id="u1"))
        assert mgr.queue_size == 0

        mgr.add_player(_make_entry(user_id="u2", connection_id="c2"))
        assert mgr.queue_size == 1

    def test_matchmaking_queue_add__when_different_users__should_queue_both(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1"))
        mgr.add_player(_make_entry(user_id="u2", connection_id="c2"))
        assert mgr.queue_size == 2


class TestRemovePlayer:
    def test_matchmaking_queue_remove__should_decrement_queue_size(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(connection_id="c1"))
        mgr.remove_player("c1")
        assert mgr.queue_size == 0

    def test_matchmaking_queue_remove__when_user_not_queued__should_do_nothing(self):
        mgr = MatchmakingManager()
        mgr.remove_player("nonexistent")
        assert mgr.queue_size == 0

    def test_matchmaking_queue_remove__should_allow_user_to_rejoin(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1"))
        mgr.remove_player("c1")
        mgr.add_player(_make_entry(user_id="u1", connection_id="c2"))
        assert mgr.queue_size == 1


class TestTryMatch:
    def test_matchmaking_try_match__when_not_enough_players__should_return_none(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS - 1):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        assert mgr.try_match() is None

    def test_matchmaking_try_match__when_enough_players__should_return_matched_players(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        matched = mgr.try_match()
        assert matched is not None
        assert len(matched) == MATCHMAKING_SEATS
        assert mgr.queue_size == 0

    def test_matchmaking_try_match__when_extra_players__should_keep_them_queued(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS + 2):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        matched = mgr.try_match()
        assert matched is not None
        assert len(matched) == MATCHMAKING_SEATS
        assert mgr.queue_size == 2

    def test_matchmaking_has_user__when_player_matched__should_count_until_the_match_is_resolved(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        assert mgr.has_user("u0") is True
        mgr.try_match()
        assert mgr.has_user("u0") is True
        mgr.clear_in_flight({f"u{i}" for i in range(MATCHMAKING_SEATS)})
        assert mgr.has_user("u0") is False
