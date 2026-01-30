"""
Unit tests for Matchmaker.
"""

from game.logic.enums import BotType
from game.logic.matchmaker import Matchmaker


class TestMatchmakerFillSeats:
    def test_fill_seats_returns_four_configs(self):
        """fill_seats with 1 human returns 4 seat configs."""
        matchmaker = Matchmaker()

        configs = matchmaker.fill_seats(["Alice"])

        assert len(configs) == 4

    def test_fill_seats_one_human_three_bots(self):
        """fill_seats with 1 human returns 1 human and 3 bot configs."""
        matchmaker = Matchmaker()

        configs = matchmaker.fill_seats(["Alice"])

        human_count = sum(1 for c in configs if c.bot_type is None)
        bot_count = sum(1 for c in configs if c.bot_type is not None)
        assert human_count == 1
        assert bot_count == 3

    def test_fill_seats_human_assigned_to_valid_seat(self):
        """Human player is assigned to a seat in range 0-3."""
        matchmaker = Matchmaker()

        configs = matchmaker.fill_seats(["Alice"])

        human_seats = [i for i, c in enumerate(configs) if c.bot_type is None]
        assert len(human_seats) == 1
        assert 0 <= human_seats[0] <= 3

    def test_fill_seats_human_name_preserved(self):
        """Human player config has the correct name."""
        matchmaker = Matchmaker()

        configs = matchmaker.fill_seats(["Alice"])

        human_configs = [c for c in configs if c.bot_type is None]
        assert human_configs[0].name == "Alice"

    def test_fill_seats_bot_names_follow_pattern(self):
        """Bot names follow 'Tsumogiri N' pattern."""
        matchmaker = Matchmaker()

        configs = matchmaker.fill_seats(["Alice"])

        bot_configs = [c for c in configs if c.bot_type is not None]
        bot_names = [c.name for c in bot_configs]
        assert bot_names == ["Tsumogiri 1", "Tsumogiri 2", "Tsumogiri 3"]

    def test_fill_seats_bots_have_tsumogiri_type(self):
        """Bot configs have bot_type=BotType.TSUMOGIRI."""
        matchmaker = Matchmaker()

        configs = matchmaker.fill_seats(["Alice"])

        for config in configs:
            if config.bot_type is not None:
                assert config.bot_type == BotType.TSUMOGIRI

    def test_fill_seats_human_has_no_bot_type(self):
        """Human config has bot_type=None."""
        matchmaker = Matchmaker()

        configs = matchmaker.fill_seats(["Alice"])

        human_configs = [c for c in configs if c.bot_type is None]
        assert human_configs[0].bot_type is None

    def test_fill_seats_different_seeds_different_assignments(self):
        """Different seeds produce different seat assignments."""
        matchmaker = Matchmaker()

        configs1 = matchmaker.fill_seats(["Alice"], seed=1.0)
        configs2 = matchmaker.fill_seats(["Alice"], seed=2.0)

        seat1 = next(i for i, c in enumerate(configs1) if c.bot_type is None)
        seat2 = next(i for i, c in enumerate(configs2) if c.bot_type is None)

        # with different seeds, seats should eventually differ
        # use seeds known to produce different results
        configs_a = matchmaker.fill_seats(["Alice"], seed=0.0)
        configs_b = matchmaker.fill_seats(["Alice"], seed=42.0)
        seat_a = next(i for i, c in enumerate(configs_a) if c.bot_type is None)
        seat_b = next(i for i, c in enumerate(configs_b) if c.bot_type is None)
        # at least one pair should differ across multiple seeds
        seats = {seat1, seat2, seat_a, seat_b}
        assert len(seats) > 1

    def test_fill_seats_same_seed_same_assignments(self):
        """Same seed produces identical seat assignments."""
        matchmaker = Matchmaker()

        configs1 = matchmaker.fill_seats(["Alice"], seed=12345.0)
        configs2 = matchmaker.fill_seats(["Alice"], seed=12345.0)

        for c1, c2 in zip(configs1, configs2, strict=True):
            assert c1.name == c2.name
            assert c1.bot_type == c2.bot_type
            assert c1.bot_type == c2.bot_type
