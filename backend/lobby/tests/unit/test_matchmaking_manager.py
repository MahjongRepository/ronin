from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from lobby.matchmaking.manager import MatchmakingManager
from lobby.matchmaking.models import MATCHMAKING_SEATS
from lobby.tests.conftest import make_player

if TYPE_CHECKING:
    from lobby.players import LobbyPlayer


def _make_entry(user_id: str = "u1", username: str = "alice", connection_id: str = "c1") -> LobbyPlayer:
    return make_player(connection_id=connection_id, user_id=user_id, username=username)


class TestAddPlayer:
    def test_matchmaking_queue_add__when_table_not_full__should_return_the_queue_position(self):
        mgr = MatchmakingManager()
        assert mgr.add_player(_make_entry(user_id="u1", connection_id="c1")) == 1
        assert mgr.add_player(_make_entry(user_id="u2", connection_id="c2")) == 2
        assert mgr.queue_size == 2

    def test_matchmaking_queue_add__when_occupancy_reports_a_conflict__should_raise_it_before_queueing(self):
        mgr = MatchmakingManager(find_conflict=lambda user_id: "already_in_room" if user_id == "u1" else None)
        with pytest.raises(ValueError, match="already_in_room"):
            mgr.add_player(_make_entry(user_id="u1"))
        assert mgr.queue_size == 0

        mgr.add_player(_make_entry(user_id="u2", connection_id="c2"))
        assert mgr.queue_size == 1

    def test_matchmaking_queue_add__when_join_fills_the_table__should_return_the_matched_players_in_order(self):
        mgr = MatchmakingManager()
        players = [_make_entry(user_id=f"u{i}", connection_id=f"c{i}") for i in range(MATCHMAKING_SEATS)]
        for player in players[:-1]:
            mgr.add_player(player)

        assert mgr.add_player(players[-1]) == players
        assert mgr.queue_size == 0


class TestRemovePlayer:
    def test_matchmaking_queue_remove__should_report_whether_it_removed_the_connection(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(connection_id="c1"))
        assert mgr.remove_player("c1") is True
        assert mgr.queue_size == 0
        assert mgr.remove_player("c1") is False

    def test_matchmaking_queue_remove__should_allow_user_to_rejoin(self):
        mgr = MatchmakingManager()
        mgr.add_player(_make_entry(user_id="u1", connection_id="c1"))
        mgr.remove_player("c1")
        mgr.add_player(_make_entry(user_id="u1", connection_id="c2"))
        assert mgr.queue_size == 1


class TestInFlight:
    def test_matchmaking_has_user__when_player_matched__should_count_until_the_match_is_resolved(self):
        mgr = MatchmakingManager()
        for i in range(MATCHMAKING_SEATS - 1):
            mgr.add_player(_make_entry(user_id=f"u{i}", connection_id=f"c{i}"))

        assert mgr.has_user("u0") is True
        mgr.add_player(_make_entry(user_id="last", connection_id="c-last"))
        assert mgr.has_user("u0") is True
        mgr.clear_in_flight({"u0", "u1", "u2", "last"})
        assert mgr.has_user("u0") is False
