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

    def test_matchmaking_queue_add__when_user_already_queued__should_raise(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1"))
        with pytest.raises(ValueError, match="already_in_queue"):
            mgr.add_player(_make_entry(user_id="u1", connection_id="c2"))

    def test_matchmaking_queue_add__when_user_is_in_a_room__should_raise_before_queueing(self):
        mgr = MatchmakingManager(is_user_in_room=lambda user_id: user_id == "u1")
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

    def test_matchmaking_try_match__should_move_matched_players_to_in_flight(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        mgr.try_match()
        # Matched players are in-flight, not in queue, but still tracked
        assert mgr.has_user("u0")
        assert mgr.has_user("u1")
        assert mgr.queue_size == 0

    def test_matchmaking_try_match__when_player_in_flight__should_reject_rejoin(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        mgr.try_match()
        with pytest.raises(ValueError, match="already_in_queue"):
            mgr.add_player(_make_entry(user_id="u0", connection_id="c_new"))

    def test_matchmaking_try_match__when_in_flight_cleared__should_allow_rejoin(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        mgr.try_match()
        mgr.clear_in_flight({"u0", "u1", "u2", "u3"})
        assert not mgr.has_user("u0")

        mgr.add_player(_make_entry(user_id="u0", connection_id="c_new"))
        assert mgr.has_user("u0")


class TestRequeueAtFront:
    def test_matchmaking_requeue__should_place_players_at_front(self):
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

    def test_matchmaking_requeue__when_user_already_queued__should_skip_them(self):
        mgr = MatchmakingManager()
        entry = _make_entry(user_id="u1", connection_id="c1")
        mgr.add_player(entry)
        mgr.requeue_at_front([entry])
        assert mgr.queue_size == 1

    def test_matchmaking_requeue__should_clear_in_flight(self):
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
    def test_matchmaking_has_user__when_user_queued__should_return_true(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1"))
        assert mgr.has_user("u1") is True

    def test_matchmaking_has_user__when_user_absent__should_return_false(self):
        mgr = MatchmakingManager()
        assert mgr.has_user("u1") is False
