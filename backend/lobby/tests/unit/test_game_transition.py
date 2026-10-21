from __future__ import annotations

from lobby.game_transition import sign_player_tickets


class TestSignPlayerTickets:
    def test_sign_player_tickets__should_produce_spec_and_ticket_per_player(self):
        players = [
            ("uid1", "alice", "conn1"),
            ("uid2", "bob", "conn2"),
        ]
        specs, ticket_map = sign_player_tickets(players=players, game_id="game-123", ticket_secret="secret")
        assert len(specs) == 2
        assert len(ticket_map) == 2

    def test_sign_player_tickets__should_key_ticket_map_by_connection_id(self):
        players = [("uid1", "alice", "conn1")]
        _specs, ticket_map = sign_player_tickets(players=players, game_id="game-123", ticket_secret="secret")
        assert "conn1" in ticket_map

    def test_sign_player_tickets__should_include_player_info_in_specs(self):
        players = [("uid1", "alice", "conn1")]
        specs, _ticket_map = sign_player_tickets(players=players, game_id="game-123", ticket_secret="secret")
        assert specs[0]["name"] == "alice"
        assert specs[0]["user_id"] == "uid1"
        assert "game_ticket" in specs[0]

    def test_sign_player_tickets__should_return_payload_dot_signature_tickets(self):
        players = [("uid1", "alice", "conn1")]
        _specs, ticket_map = sign_player_tickets(players=players, game_id="game-123", ticket_secret="secret")
        ticket = ticket_map["conn1"]
        # Signed ticket format: base64url(payload).base64url(signature)
        assert "." in ticket
        parts = ticket.split(".")
        assert len(parts) == 2

    def test_sign_player_tickets__when_different_connections__should_issue_different_tickets(self):
        players = [
            ("uid1", "alice", "conn1"),
            ("uid2", "bob", "conn2"),
        ]
        _specs, ticket_map = sign_player_tickets(players=players, game_id="game-123", ticket_secret="secret")
        assert ticket_map["conn1"] != ticket_map["conn2"]
