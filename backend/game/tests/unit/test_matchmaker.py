"""
Unit tests for Matchmaker.
"""

import pytest

from game.logic.enums import AIPlayerType
from game.logic.matchmaker import fill_seats


class TestFillSeats:
    def test_fill_seats_one_player_three_ai_players(self):
        """fill_seats with 1 player returns 1 player (correct name) and 3 AI player configs."""
        configs = fill_seats(["Alice"])

        assert len(configs) == 4
        player_configs = [c for c in configs if c.ai_player_type is None]
        ai_player_configs = [c for c in configs if c.ai_player_type is not None]
        assert len(player_configs) == 1
        assert len(ai_player_configs) == 3
        assert player_configs[0].name == "Alice"

    def test_fill_seats_ai_player_names_and_type(self):
        """AI player configs follow 'Tsumogiri N' naming and have TSUMOGIRI type."""
        configs = fill_seats(["Alice"])

        ai_player_configs = [c for c in configs if c.ai_player_type is not None]
        assert [c.name for c in ai_player_configs] == ["Tsumogiri 1", "Tsumogiri 2", "Tsumogiri 3"]
        assert all(c.ai_player_type == AIPlayerType.TSUMOGIRI for c in ai_player_configs)

    def test_fill_seats_different_seeds_different_assignments(self):
        """Different seeds produce different seat assignments."""
        seats = set()
        for seed in ["a" * 192, "b" * 192, "c" * 192, "d" * 192]:
            configs = fill_seats(["Alice"], seed=seed)
            seat = next(i for i, c in enumerate(configs) if c.ai_player_type is None)
            seats.add(seat)

        assert len(seats) > 1

    def test_fill_seats_same_seed_same_assignments(self):
        """Same seed produces identical seat assignments."""
        configs1 = fill_seats(["Alice"], seed="a" * 192)
        configs2 = fill_seats(["Alice"], seed="a" * 192)

        for c1, c2 in zip(configs1, configs2, strict=True):
            assert c1.name == c2.name
            assert c1.ai_player_type == c2.ai_player_type


class TestFillSeatsFourPlayers:
    """Tests for fill_seats with 4 players (PVP mode)."""

    def test_four_players_all_seats_player(self):
        """4 players: all seats assigned to players with correct names, 0 AI players."""
        names = ["Alice", "Bob", "Charlie", "Dave"]

        configs = fill_seats(names)

        assert len(configs) == 4
        assert all(c.ai_player_type is None for c in configs)
        assert {c.name for c in configs} == set(names)


class TestFillSeatsValidation:
    """Tests for fill_seats input validation."""

    def test_empty_player_names_raises(self):
        """Empty player list raises ValueError."""
        with pytest.raises(ValueError, match="Expected 1 to 4"):
            fill_seats([])

    def test_too_many_players_raises(self):
        """More than 4 players raises ValueError."""
        with pytest.raises(ValueError, match="Expected 1 to 4"):
            fill_seats(["A", "B", "C", "D", "E"])

    def test_duplicate_names_raises(self):
        """Duplicate player names raises ValueError."""
        with pytest.raises(ValueError, match="unique"):
            fill_seats(["Alice", "Alice"])

    def test_empty_name_raises(self):
        """Empty string player name raises ValueError."""
        with pytest.raises(ValueError, match="empty or whitespace"):
            fill_seats([""])

    def test_whitespace_name_raises(self):
        """Whitespace-only player name raises ValueError."""
        with pytest.raises(ValueError, match="empty or whitespace"):
            fill_seats(["  "])

    def test_ai_player_name_collision_raises(self):
        """Player named 'Tsumogiri 1' with 3 AI players raises ValueError."""
        with pytest.raises(ValueError, match="AI player names"):
            fill_seats(["Tsumogiri 1"])

    def test_no_collision_with_four_players(self):
        """'Tsumogiri 1' with 4 players (0 AI) is valid since no AI players are generated."""
        configs = fill_seats(["Tsumogiri 1", "Tsumogiri 2", "Tsumogiri 3", "Alice"])
        assert len(configs) == 4
        assert all(c.ai_player_type is None for c in configs)

    def test_no_collision_when_name_doesnt_match_generated_ai(self):
        """'Tsumogiri 4' with 3 AI players is valid since AI names are Tsumogiri 1-3."""
        configs = fill_seats(["Tsumogiri 4"])
        assert len(configs) == 4
