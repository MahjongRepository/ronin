"""
Unit tests for Matchmaker.
"""

from game.logic.enums import BotType
from game.logic.matchmaker import fill_seats


class TestFillSeats:
    def test_fill_seats_one_human_three_bots(self):
        """fill_seats with 1 human returns 1 human (correct name) and 3 bot configs."""
        configs = fill_seats(["Alice"])

        assert len(configs) == 4
        human_configs = [c for c in configs if c.bot_type is None]
        bot_configs = [c for c in configs if c.bot_type is not None]
        assert len(human_configs) == 1
        assert len(bot_configs) == 3
        assert human_configs[0].name == "Alice"

    def test_fill_seats_bot_names_and_type(self):
        """Bot configs follow 'Tsumogiri N' naming and have TSUMOGIRI type."""
        configs = fill_seats(["Alice"])

        bot_configs = [c for c in configs if c.bot_type is not None]
        assert [c.name for c in bot_configs] == ["Tsumogiri 1", "Tsumogiri 2", "Tsumogiri 3"]
        assert all(c.bot_type == BotType.TSUMOGIRI for c in bot_configs)

    def test_fill_seats_different_seeds_different_assignments(self):
        """Different seeds produce different seat assignments."""
        seats = set()
        for seed in [0.0, 1.0, 2.0, 42.0]:
            configs = fill_seats(["Alice"], seed=seed)
            seat = next(i for i, c in enumerate(configs) if c.bot_type is None)
            seats.add(seat)

        assert len(seats) > 1

    def test_fill_seats_same_seed_same_assignments(self):
        """Same seed produces identical seat assignments."""
        configs1 = fill_seats(["Alice"], seed=12345.0)
        configs2 = fill_seats(["Alice"], seed=12345.0)

        for c1, c2 in zip(configs1, configs2, strict=True):
            assert c1.name == c2.name
            assert c1.bot_type == c2.bot_type


class TestFillSeatsFourHumans:
    """Tests for fill_seats with 4 human players (PVP mode)."""

    def test_four_humans_all_seats_human(self):
        """4 humans: all seats assigned to humans with correct names, 0 bots."""
        names = ["Alice", "Bob", "Charlie", "Dave"]

        configs = fill_seats(names)

        assert len(configs) == 4
        assert all(c.bot_type is None for c in configs)
        assert {c.name for c in configs} == set(names)

    def test_four_humans_with_seed_randomizes_seats(self):
        """4 humans with seed: names are randomly assigned to seats (not always input order)."""
        names = ["Alice", "Bob", "Charlie", "Dave"]

        orderings: set[tuple[str, ...]] = set()
        for seed in [0.0, 1.0, 2.0, 42.0, 100.0]:
            configs = fill_seats(names, seed=seed)
            orderings.add(tuple(c.name for c in configs))

        assert len(orderings) > 1, "different seeds should produce different seat assignments"

    def test_four_humans_same_seed_deterministic(self):
        """4 humans with same seed: deterministic seat assignment."""
        names = ["Alice", "Bob", "Charlie", "Dave"]

        configs1 = fill_seats(names, seed=12345.0)
        configs2 = fill_seats(names, seed=12345.0)

        for c1, c2 in zip(configs1, configs2, strict=True):
            assert c1.name == c2.name
            assert c1.bot_type == c2.bot_type
