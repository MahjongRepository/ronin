import pytest

from game.logic.enums import AIPlayerType
from game.logic.matchmaker import fill_seats


class TestFillSeats:
    def test_fill_seats__when_one_player__should_add_three_ai_players(self):
        configs = fill_seats(["Alice"])

        assert len(configs) == 4
        player_configs = [c for c in configs if c.ai_player_type is None]
        ai_player_configs = [c for c in configs if c.ai_player_type is not None]
        assert len(player_configs) == 1
        assert len(ai_player_configs) == 3
        assert player_configs[0].name == "Alice"

    def test_fill_seats__when_one_player__should_name_ai_players_tsumogiri_n(self):
        configs = fill_seats(["Alice"])

        ai_player_configs = [c for c in configs if c.ai_player_type is not None]
        assert [c.name for c in ai_player_configs] == ["Tsumogiri 1", "Tsumogiri 2", "Tsumogiri 3"]
        assert all(c.ai_player_type == AIPlayerType.TSUMOGIRI for c in ai_player_configs)

    def test_fill_seats__when_seeds_differ__should_vary_player_seat(self):
        seats = set()
        for seed in ["a" * 192, "b" * 192, "c" * 192, "d" * 192]:
            configs = fill_seats(["Alice"], seed=seed)
            seat = next(i for i, c in enumerate(configs) if c.ai_player_type is None)
            seats.add(seat)

        assert len(seats) > 1

    def test_fill_seats__when_same_seed__should_assign_same_seats(self):
        configs1 = fill_seats(["Alice"], seed="a" * 192)
        configs2 = fill_seats(["Alice"], seed="a" * 192)

        for c1, c2 in zip(configs1, configs2, strict=True):
            assert c1.name == c2.name
            assert c1.ai_player_type == c2.ai_player_type


class TestFillSeatsFourPlayers:
    def test_fill_seats__when_four_players__should_seat_all_as_players(self):
        names = ["Alice", "Bob", "Charlie", "Dave"]

        configs = fill_seats(names)

        assert len(configs) == 4
        assert all(c.ai_player_type is None for c in configs)
        assert {c.name for c in configs} == set(names)


class TestFillSeatsValidation:
    def test_fill_seats__when_no_players__should_raise(self):
        with pytest.raises(ValueError, match="Expected 1 to 4"):
            fill_seats([])

    def test_fill_seats__when_more_than_four_players__should_raise(self):
        with pytest.raises(ValueError, match="Expected 1 to 4"):
            fill_seats(["A", "B", "C", "D", "E"])

    def test_fill_seats__when_names_duplicate__should_raise(self):
        with pytest.raises(ValueError, match="unique"):
            fill_seats(["Alice", "Alice"])

    def test_fill_seats__when_name_is_empty__should_raise(self):
        with pytest.raises(ValueError, match="empty or whitespace"):
            fill_seats([""])

    def test_fill_seats__when_name_is_whitespace__should_raise(self):
        with pytest.raises(ValueError, match="empty or whitespace"):
            fill_seats(["  "])

    def test_fill_seats__when_name_collides_with_ai_name__should_raise(self):
        with pytest.raises(ValueError, match="AI player names"):
            fill_seats(["Tsumogiri 1"])

    def test_fill_seats__when_four_players_use_ai_style_names__should_not_raise(self):
        configs = fill_seats(["Tsumogiri 1", "Tsumogiri 2", "Tsumogiri 3", "Alice"])
        assert len(configs) == 4
        assert all(c.ai_player_type is None for c in configs)

    def test_fill_seats__when_name_not_matching_generated_ai__should_not_raise(self):
        configs = fill_seats(["Tsumogiri 4"])
        assert len(configs) == 4
