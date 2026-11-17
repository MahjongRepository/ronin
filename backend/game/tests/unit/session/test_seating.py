from game.engine import SEED_BYTES, determine_first_dealer, seat_permutation, validate_seed_hex
from game.session.seating import generate_seed, seat_players

SEED = "a" * 192


class TestGenerateSeed:
    def test_generate_seed__when_called_twice__should_return_two_different_valid_seeds(self):
        first, second = generate_seed(), generate_seed()
        validate_seed_hex(first)
        assert len(bytes.fromhex(first)) == SEED_BYTES
        assert first != second


class TestSeatPlayers:
    def test_seat_players__when_one_player__should_seat_three_ai_players_named_tsumogiri_n_in_seat_order(self):
        seating = seat_players(["Alice"], SEED)
        (alice_seat,) = seating.player_seats
        assert alice_seat == seat_permutation(SEED)[0]
        assert seating.names[alice_seat] == "Alice"
        assert [seating.names[seat] for seat in sorted(seating.ai_seats)] == [
            "ai-tsumogiri-1",
            "ai-tsumogiri-2",
            "ai-tsumogiri-3",
        ]
        assert seating.ai_seats == frozenset(range(4)) - {alice_seat}

    def test_seat_players__when_player_is_named_like_an_ai__should_skip_their_name_for_ai_players(self):
        seating = seat_players(["ai-tsumogiri-1"], SEED)
        assert sorted(seating.names[seat] for seat in seating.ai_seats) == [
            "ai-tsumogiri-2",
            "ai-tsumogiri-3",
            "ai-tsumogiri-4",
        ]
        assert seating.names[seating.player_seats[0]] == "ai-tsumogiri-1"

    def test_seat_players__when_four_players__should_seat_each_at_its_permutation_entry_in_input_order(self):
        names = ["Alice", "Bob", "Charlie", "Dave"]

        seating = seat_players(names, "ab" * 96)
        assert seating.player_seats == seat_permutation("ab" * 96)
        assert seating.player_seats != (0, 1, 2, 3)
        assert seating.ai_seats == frozenset()
        assert [seating.names[seat] for seat in seating.player_seats] == names

    def test_seat_players__when_fixed_seats__should_seat_players_in_wind_order_from_the_first_dealer(self):
        names = ["Alice", "Bob", "Charlie", "Dave"]
        seed = "e" * 192
        assert determine_first_dealer(seed)[0] == 3
        assert seat_permutation(seed) != (3, 0, 1, 2)

        seating = seat_players(names, seed, fixed_seats=True)
        assert seating.player_seats == (3, 0, 1, 2)
        assert seating.names == ("Bob", "Charlie", "Dave", "Alice")
        assert seating.ai_seats == frozenset()
