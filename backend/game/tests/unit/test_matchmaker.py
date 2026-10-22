import pytest

from game.logic.enums import AIPlayerType
from game.logic.matchmaker import fill_seats


class TestFillSeats:
    def test_fill_seats__when_one_player__should_add_three_ai_players(self):
        configs, seats = fill_seats(["Alice"])
        assert len(configs) == 4
        player_configs = [c for c in configs if c.ai_player_type is None]
        ai_player_configs = [c for c in configs if c.ai_player_type is not None]
        assert len(player_configs) == 1
        assert len(ai_player_configs) == 3
        assert configs[seats[0]].name == "Alice"

    def test_fill_seats__when_one_player__should_name_ai_players_tsumogiri_n(self):
        configs, _seats = fill_seats(["Alice"])
        ai_player_configs = [c for c in configs if c.ai_player_type is not None]
        assert [c.name for c in ai_player_configs] == ["Tsumogiri 1", "Tsumogiri 2", "Tsumogiri 3"]
        assert all(c.ai_player_type == AIPlayerType.TSUMOGIRI for c in ai_player_configs)

    def test_fill_seats__when_player_is_named_like_an_ai__should_skip_their_name_for_ai_players(self):
        configs, seats = fill_seats(["Tsumogiri 1"], seed="a" * 192)
        ai_player_names = [c.name for c in configs if c.ai_player_type is not None]
        assert ai_player_names == ["Tsumogiri 2", "Tsumogiri 3", "Tsumogiri 4"]
        assert configs[seats[0]].name == "Tsumogiri 1"
        assert configs[seats[0]].ai_player_type is None

    def test_fill_seats__when_seeds_differ__should_vary_player_seat(self):
        seats = set()
        for seed in ["a" * 192, "b" * 192, "c" * 192, "d" * 192]:
            _configs, player_seats = fill_seats(["Alice"], seed=seed)
            seats.add(player_seats[0])

        assert len(seats) > 1

    def test_fill_seats__when_same_seed__should_assign_same_seats(self):
        configs1, seats1 = fill_seats(["Alice"], seed="a" * 192)
        configs2, seats2 = fill_seats(["Alice"], seed="a" * 192)
        assert seats1 == seats2
        for c1, c2 in zip(configs1, configs2, strict=True):
            assert c1.name == c2.name
            assert c1.ai_player_type == c2.ai_player_type


class TestFillSeatsFourPlayers:
    def test_fill_seats__when_four_players__should_seat_each_input_player_at_its_returned_seat(self):
        names = ["Alice", "Bob", "Charlie", "Dave"]

        configs, seats = fill_seats(names, seed="a" * 192)
        assert sorted(seats) == [0, 1, 2, 3]
        assert seats != (0, 1, 2, 3)
        assert all(c.ai_player_type is None for c in configs)
        assert [configs[seat].name for seat in seats] == names


class TestFillSeatsValidation:
    def test_fill_seats__when_no_players__should_raise(self):
        with pytest.raises(ValueError, match="Expected 1 to 4"):
            fill_seats([])

    def test_fill_seats__when_more_than_four_players__should_raise(self):
        with pytest.raises(ValueError, match="Expected 1 to 4"):
            fill_seats(["A", "B", "C", "D", "E"])
