import pytest

from game.logic.rng import (
    PCG64DXSM,
    SEED_BYTES,
    _bounded_uint64,
    _derive_round_pcg,
    _fisher_yates_shuffle,
    create_seat_rng,
    determine_first_dealer,
    generate_seed,
    generate_shuffled_wall_and_dice,
    roll_dice,
    validate_seed_hex,
)
from game.logic.tiles import NUM_TILES

# A fixed seed for deterministic tests (192 hex chars = 96 bytes)
FIXED_SEED = "ab" * SEED_BYTES


class TestGenerateSeed:
    def test_generate_seed__should_return_hex_of_seed_length(self):
        seed = generate_seed()
        assert len(seed) == SEED_BYTES * 2
        decoded = bytes.fromhex(seed)
        assert len(decoded) == SEED_BYTES

    def test_generate_seed__when_called_twice__should_return_different_seeds(self):
        assert generate_seed() != generate_seed()


class TestValidateSeedHex:
    def test_validate_seed_hex__when_uppercase_hex__should_accept(self):
        validate_seed_hex(FIXED_SEED.upper())

    def test_validate_seed_hex__when_wrong_length__should_raise(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            validate_seed_hex("ab" * 10)

    def test_validate_seed_hex__when_non_hex_characters__should_raise(self):
        bad_seed = "zz" + "ab" * (SEED_BYTES - 1)
        with pytest.raises(ValueError, match="invalid hex"):
            validate_seed_hex(bad_seed)


class TestPCG64DXSM:
    def test_pcg64dxsm__when_same_state__should_yield_same_outputs(self):
        pcg1 = PCG64DXSM(state=42, increment=17)
        pcg2 = PCG64DXSM(state=42, increment=17)
        for _ in range(100):
            assert pcg1.next_uint64() == pcg2.next_uint64()

    def test_pcg64dxsm__when_zero_state__should_match_reference_vector(self):
        pcg = PCG64DXSM(state=0, increment=0)
        first_five = [pcg.next_uint64() for _ in range(5)]
        assert first_five == [
            1119539158285122193,
            13707551916819974326,
            9586226176587887866,
            3349395263454865025,
            7126510863787856555,
        ]


class TestDeriveRoundPCG:
    def test_derive_round_pcg__when_same_seed_and_round__should_yield_same_outputs(self):
        pcg1 = _derive_round_pcg(FIXED_SEED, 0)
        pcg2 = _derive_round_pcg(FIXED_SEED, 0)
        for _ in range(10):
            assert pcg1.next_uint64() == pcg2.next_uint64()

    def test_derive_round_pcg__when_prior_rounds_drawn__should_not_change_output(self):
        pcg_direct = _derive_round_pcg(FIXED_SEED, 5)
        direct_output = pcg_direct.next_uint64()

        for r in range(5):
            pcg_prior = _derive_round_pcg(FIXED_SEED, r)
            for _ in range(100):
                pcg_prior.next_uint64()

        pcg_after = _derive_round_pcg(FIXED_SEED, 5)
        after_output = pcg_after.next_uint64()
        assert direct_output == after_output

    def test_derive_round_pcg__when_different_rounds__should_yield_different_outputs(self):
        pcg0 = _derive_round_pcg(FIXED_SEED, 0)
        pcg1 = _derive_round_pcg(FIXED_SEED, 1)
        assert pcg0.next_uint64() != pcg1.next_uint64()

    def test_derive_round_pcg__when_round_negative__should_raise(self):
        with pytest.raises(ValueError, match=r"\[0, 2\^32\)"):
            _derive_round_pcg(FIXED_SEED, -1)

    def test_derive_round_pcg__when_round_exceeds_uint32__should_raise(self):
        with pytest.raises(ValueError, match=r"\[0, 2\^32\)"):
            _derive_round_pcg(FIXED_SEED, 2**32)

    def test_derive_round_pcg__when_seed_invalid__should_raise(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            _derive_round_pcg("short", 0)


class TestBoundedUint64:
    def test_bounded_uint64__when_bound_valid__should_return_value_below_bound(self):
        pcg = PCG64DXSM(state=42, increment=17)
        for bound in [1, 2, 6, 136, 1000]:
            for _ in range(200):
                val = _bounded_uint64(pcg, bound)
                assert 0 <= val < bound

    def test_bounded_uint64__when_bound_zero__should_raise(self):
        pcg = PCG64DXSM(state=1, increment=1)
        with pytest.raises(ValueError, match=r"bound must be in"):
            _bounded_uint64(pcg, 0)

    def test_bounded_uint64__when_bound_exceeds_2_pow_64__should_raise(self):
        pcg = PCG64DXSM(state=1, increment=1)
        with pytest.raises(ValueError, match=r"bound must be in"):
            _bounded_uint64(pcg, (1 << 64) + 1)

    def test_bounded_uint64__when_bound_exactly_2_pow_64__should_succeed(self):
        pcg = PCG64DXSM(state=42, increment=17)
        result = _bounded_uint64(pcg, 1 << 64)
        assert 0 <= result < (1 << 64)


class TestFisherYatesShuffle:
    def test_fisher_yates_shuffle__should_return_permutation(self):
        pcg = PCG64DXSM(state=12345, increment=67890)
        tiles = list(range(NUM_TILES))

        shuffled = _fisher_yates_shuffle(tiles, pcg)
        assert sorted(shuffled) == list(range(NUM_TILES))

    def test_fisher_yates_shuffle__when_same_pcg_state__should_shuffle_identically(self):
        tiles = list(range(20))
        pcg1 = PCG64DXSM(state=555, increment=777)
        pcg2 = PCG64DXSM(state=555, increment=777)

        assert _fisher_yates_shuffle(tiles, pcg1) == _fisher_yates_shuffle(tiles, pcg2)


class TestCreateSeatRng:
    def test_create_seat_rng__when_same_seed__should_sample_same_seats(self):
        rng1 = create_seat_rng(FIXED_SEED)
        rng2 = create_seat_rng(FIXED_SEED)

        seats1 = rng1.sample(range(4), 4)
        seats2 = rng2.sample(range(4), 4)
        assert seats1 == seats2


class TestPCG64DXSMReferenceVector:
    def test_derive_round_pcg__when_fixed_seed_round_0__should_match_reference_outputs(self):
        pcg = _derive_round_pcg(FIXED_SEED, 0)
        outputs = [pcg.next_uint64() for _ in range(5)]
        assert outputs == [
            4560994182688879067,
            7143896276016910997,
            3217883979251399464,
            6070462904197123079,
            14562757223433895540,
        ]


class TestRollDice:
    def test_roll_dice__should_return_dice_between_1_and_6(self):
        pcg = PCG64DXSM(state=42, increment=17)
        for _ in range(100):
            die1, die2 = roll_dice(pcg)
            assert 1 <= die1 <= 6
            assert 1 <= die2 <= 6

    def test_roll_dice__when_same_pcg_state__should_roll_same_dice(self):
        pcg1 = PCG64DXSM(state=123, increment=456)
        pcg2 = PCG64DXSM(state=123, increment=456)
        assert roll_dice(pcg1) == roll_dice(pcg2)


class TestGenerateShuffledWallAndDice:
    def test_generate_shuffled_wall_and_dice__when_same_seed_and_round__should_be_identical(self):
        wall1, dice1 = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        wall2, dice2 = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert wall1 == wall2
        assert dice1 == dice2

    def test_generate_shuffled_wall_and_dice__should_return_full_tile_permutation(self):
        wall, _ = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert len(wall) == NUM_TILES
        assert sorted(wall) == list(range(NUM_TILES))

    def test_generate_shuffled_wall_and_dice__should_return_dice_between_1_and_6(self):
        _, dice = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert 1 <= dice[0] <= 6
        assert 1 <= dice[1] <= 6


class TestDetermineFirstDealer:
    def test_determine_first_dealer__when_same_seed__should_return_same_result(self):
        result1 = determine_first_dealer(FIXED_SEED)
        result2 = determine_first_dealer(FIXED_SEED)
        assert result1 == result2

    def test_determine_first_dealer__should_return_dealer_between_0_and_3(self):
        dealer, _, _ = determine_first_dealer(FIXED_SEED)
        assert 0 <= dealer <= 3

    def test_determine_first_dealer__should_return_dice_between_1_and_6(self):
        _, first_dice, second_dice = determine_first_dealer(FIXED_SEED)
        for die in (*first_dice, *second_dice):
            assert 1 <= die <= 6

    def test_determine_first_dealer__should_apply_second_roll_to_first_roll_seat(self):
        dealer, first_dice, second_dice = determine_first_dealer(FIXED_SEED)
        temp_dealer = (sum(first_dice) - 1) % 4
        expected_dealer = (temp_dealer + sum(second_dice) - 1) % 4
        assert dealer == expected_dealer
