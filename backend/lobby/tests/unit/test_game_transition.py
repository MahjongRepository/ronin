"""Unit tests for shared game transition logic."""

from __future__ import annotations

from lobby.game_transition import sign_player_tickets


class TestSignPlayerTickets:
    def test_produces_correct_number_of_specs(self):
        players = [
            ("uid1", "alice", "conn1"),
            ("uid2", "bob", "conn2"),
        ]
        specs, ticket_map = sign_player_tickets(players, "game-123", "secret")
        assert len(specs) == 2
        assert len(ticket_map) == 2

    def test_ticket_map_keys_are_connection_ids(self):
        players = [("uid1", "alice", "conn1")]
        _specs, ticket_map = sign_player_tickets(players, "game-123", "secret")
        assert "conn1" in ticket_map

    def test_specs_contain_player_info(self):
        players = [("uid1", "alice", "conn1")]
        specs, _ticket_map = sign_player_tickets(players, "game-123", "secret")
        assert specs[0]["name"] == "alice"
        assert specs[0]["user_id"] == "uid1"
        assert "game_ticket" in specs[0]

    def test_tickets_are_signed_strings(self):
        players = [("uid1", "alice", "conn1")]
        _specs, ticket_map = sign_player_tickets(players, "game-123", "secret")
        ticket = ticket_map["conn1"]
        # Signed ticket format: base64url(payload).base64url(signature)
        assert "." in ticket
        parts = ticket.split(".")
        assert len(parts) == 2

    def test_different_connection_ids_get_different_tickets(self):
        players = [
            ("uid1", "alice", "conn1"),
            ("uid2", "bob", "conn2"),
        ]
        _specs, ticket_map = sign_player_tickets(players, "game-123", "secret")
        assert ticket_map["conn1"] != ticket_map["conn2"]
