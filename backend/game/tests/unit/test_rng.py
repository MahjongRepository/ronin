import hashlib
from itertools import product

import pytest

from game.logic.rng import (
    SEED_BYTES,
    WordStream,
    bounded_uint,
    create_seat_rng,
    determine_first_dealer,
    fisher_yates_shuffle,
    generate_seed,
    generate_shuffled_wall_and_dice,
    roll_dice,
    validate_seed_hex,
)
from game.logic.tiles import NUM_TILES

FIXED_SEED = "ab" * SEED_BYTES
UINT64_BOUND = 1 << 64


class ScriptedWords:
    def __init__(self, words: list[int]) -> None:
        self._words = iter(words)

    def next_uint64(self) -> int:
        return next(self._words)


class TestGenerateSeed:
    def test_generate_seed__should_return_hex_of_seed_length(self):
        seed = generate_seed()
        assert len(seed) == SEED_BYTES * 2
        assert len(bytes.fromhex(seed)) == SEED_BYTES

    def test_generate_seed__when_called_twice__should_return_different_seeds(self):
        assert generate_seed() != generate_seed()


class TestValidateSeedHex:
    def test_validate_seed_hex__when_uppercase_hex__should_accept(self):
        validate_seed_hex(FIXED_SEED.upper())

    def test_validate_seed_hex__when_wrong_length__should_raise(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            validate_seed_hex("ab" * 10)

    def test_validate_seed_hex__when_non_hex_characters__should_raise(self):
        with pytest.raises(ValueError, match="invalid hex"):
            validate_seed_hex("zz" + "ab" * (SEED_BYTES - 1))

    def test_validate_seed_hex__when_whitespace_padded__should_raise(self):
        with pytest.raises(ValueError, match="invalid hex"):
            validate_seed_hex("  " + "ab" * (SEED_BYTES - 1))


class TestWordStream:
    def test_word_stream__when_read__should_match_little_endian_shake256_of_domain_and_data(self):
        stream = WordStream(b"domain:", b"data")
        expected = int.from_bytes(hashlib.shake_256(b"domain:data").digest(8), byteorder="little")
        assert stream.next_uint64() == expected

    def test_word_stream__when_read_past_initial_prefix__should_continue_the_same_digest(self):
        stream = WordStream(b"domain:", b"data")
        words = [stream.next_uint64() for _ in range(500)]
        digest = hashlib.shake_256(b"domain:data").digest(8 * 500)
        assert words == [int.from_bytes(digest[i * 8 : i * 8 + 8], byteorder="little") for i in range(500)]

    def test_word_stream__when_domains_differ__should_yield_different_words(self):
        assert WordStream(b"a:", b"data").next_uint64() != WordStream(b"b:", b"data").next_uint64()


class TestBoundedUint:
    def test_bounded_uint__when_word_in_partial_bucket__should_reject_it_and_read_the_next(self):
        limit = UINT64_BOUND - (UINT64_BOUND % 6)
        words = ScriptedWords([limit, UINT64_BOUND - 1, limit - 1])
        assert bounded_uint(words, 6) == (limit - 1) % 6
        with pytest.raises(StopIteration):
            words.next_uint64()

    def test_bounded_uint__when_bound_divides_word_space__should_accept_every_word(self):
        assert bounded_uint(ScriptedWords([UINT64_BOUND - 1]), 1 << 64) == UINT64_BOUND - 1
        assert bounded_uint(ScriptedWords([UINT64_BOUND - 1]), 16) == 15

    def test_bounded_uint__when_bound_out_of_range__should_raise(self):
        with pytest.raises(ValueError, match="bound must be in"):
            bounded_uint(ScriptedWords([0]), 0)

        with pytest.raises(ValueError, match="bound must be in"):
            bounded_uint(ScriptedWords([0]), UINT64_BOUND + 1)


class TestFisherYatesShuffle:
    def test_fisher_yates_shuffle__when_every_choice_sequence_enumerated__should_hit_each_permutation_once(self):
        permutations = [
            tuple(fisher_yates_shuffle([0, 1, 2], ScriptedWords([j, k]))) for j, k in product(range(3), range(2))
        ]
        assert sorted(permutations) == sorted(set(permutations))
        assert len(permutations) == 6

    def test_fisher_yates_shuffle__when_seeded_from_stream__should_return_permutation_of_all_tiles(self):
        shuffled = fisher_yates_shuffle(list(range(NUM_TILES)), WordStream(b"t:", b"x"))
        assert sorted(shuffled) == list(range(NUM_TILES))
        assert shuffled != list(range(NUM_TILES))


class TestRollDice:
    def test_roll_dice__when_words_scripted__should_map_each_word_to_a_die_face(self):
        assert roll_dice(ScriptedWords([0, 5])) == (1, 6)
        assert roll_dice(ScriptedWords([7, 11])) == (2, 6)


class TestGenerateShuffledWallAndDice:
    def test_generate_shuffled_wall_and_dice__when_fixed_seed__should_match_pinned_vector(self):
        wall, dice = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert wall[:8] == [113, 56, 116, 33, 121, 40, 115, 39]
        assert dice == (5, 5)
        assert sorted(wall) == list(range(NUM_TILES))

    def test_generate_shuffled_wall_and_dice__when_rounds_differ__should_produce_different_walls(self):
        wall0, _ = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        wall1, _ = generate_shuffled_wall_and_dice(FIXED_SEED, 1)
        assert wall0 != wall1

    def test_generate_shuffled_wall_and_dice__when_round_out_of_range__should_raise(self):
        with pytest.raises(ValueError, match=r"\[0, 2\^32\)"):
            generate_shuffled_wall_and_dice(FIXED_SEED, -1)

        with pytest.raises(ValueError, match=r"\[0, 2\^32\)"):
            generate_shuffled_wall_and_dice(FIXED_SEED, 2**32)

    def test_generate_shuffled_wall_and_dice__when_seed_invalid__should_raise(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            generate_shuffled_wall_and_dice("short", 0)


class TestDetermineFirstDealer:
    def test_determine_first_dealer__when_fixed_seed__should_match_pinned_vector(self):
        assert determine_first_dealer(FIXED_SEED) == (0, (2, 2), (5, 1))

    def test_determine_first_dealer__should_apply_second_roll_to_first_roll_seat(self):
        dealer, first_dice, second_dice = determine_first_dealer(FIXED_SEED)
        temp_dealer = (sum(first_dice) - 1) % 4
        assert dealer == (temp_dealer + sum(second_dice) - 1) % 4

    def test_determine_first_dealer__when_seed_invalid__should_raise(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            determine_first_dealer("short")


class TestCreateSeatRng:
    def test_create_seat_rng__when_same_seed__should_sample_same_seats(self):
        assert create_seat_rng(FIXED_SEED).sample(range(4), 4) == create_seat_rng(FIXED_SEED).sample(range(4), 4)
