"""
Unit tests for random number generation module.

Covers PCG64DXSM determinism, Fisher-Yates correctness, seed generation,
validation, bounded sampling, and reference vector regression tests.
"""

import pytest

from game.logic.rng import (
    PCG64DXSM,
    RNG_VERSION,
    SEED_BYTES,
    TOTAL_WALL_SIZE,
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

# A fixed seed for deterministic tests (192 hex chars = 96 bytes)
FIXED_SEED = "ab" * SEED_BYTES


class TestGenerateSeed:
    def test_length(self):
        """Seed is 192 hex characters (96 bytes / 768 bits)."""
        seed = generate_seed()
        assert len(seed) == SEED_BYTES * 2

    def test_uniqueness(self):
        """Two calls produce different seeds."""
        seed1 = generate_seed()
        seed2 = generate_seed()
        assert seed1 != seed2

    def test_is_valid_hex(self):
        """Generated seed can be decoded as hex."""
        seed = generate_seed()
        decoded = bytes.fromhex(seed)
        assert len(decoded) == SEED_BYTES


class TestValidateSeedHex:
    def test_accepts_valid_seed(self):
        """Valid 192-char hex seed passes validation."""
        validate_seed_hex(FIXED_SEED)

    def test_accepts_uppercase_hex(self):
        """Uppercase hex characters are accepted."""
        validate_seed_hex(FIXED_SEED.upper())

    def test_rejects_wrong_length_short(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            validate_seed_hex("ab" * 10)

    def test_rejects_wrong_length_long(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            validate_seed_hex("ab" * 100)

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            validate_seed_hex("")

    def test_rejects_non_hex_characters(self):
        """Seed with non-hex characters is rejected."""
        bad_seed = "zz" + "ab" * (SEED_BYTES - 1)
        with pytest.raises(ValueError, match="invalid hex"):
            validate_seed_hex(bad_seed)


class TestPCG64DXSM:
    def test_deterministic(self):
        """Same state + increment produces the same output sequence."""
        pcg1 = PCG64DXSM(state=42, increment=17)
        pcg2 = PCG64DXSM(state=42, increment=17)
        for _ in range(100):
            assert pcg1.next_uint64() == pcg2.next_uint64()

    def test_output_range(self):
        """All outputs are valid uint64 values (0 to 2^64-1)."""
        pcg = PCG64DXSM(state=12345, increment=67890)
        for _ in range(1000):
            val = pcg.next_uint64()
            assert 0 <= val < (1 << 64)

    def test_period_no_immediate_repeat(self):
        """1000 consecutive outputs are all distinct."""
        pcg = PCG64DXSM(state=99999, increment=11111)
        outputs = [pcg.next_uint64() for _ in range(1000)]
        assert len(set(outputs)) == 1000

    def test_different_state_different_output(self):
        """Different state values produce different output sequences."""
        pcg1 = PCG64DXSM(state=1, increment=1)
        pcg2 = PCG64DXSM(state=2, increment=1)
        outputs1 = [pcg1.next_uint64() for _ in range(10)]
        outputs2 = [pcg2.next_uint64() for _ in range(10)]
        assert outputs1 != outputs2

    def test_different_increment_different_output(self):
        """Different increment values produce different output sequences."""
        pcg1 = PCG64DXSM(state=1, increment=1)
        pcg2 = PCG64DXSM(state=1, increment=2)
        outputs1 = [pcg1.next_uint64() for _ in range(10)]
        outputs2 = [pcg2.next_uint64() for _ in range(10)]
        assert outputs1 != outputs2

    def test_reference_vector(self):
        """Fixed state+increment yields exact expected outputs (regression guard).

        Hardcoded reference values detect any change to the PCG algorithm,
        constants, or initialization sequence.
        """
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
    def test_deterministic(self):
        """Same seed + round produces the same PCG output."""
        pcg1 = _derive_round_pcg(FIXED_SEED, 0)
        pcg2 = _derive_round_pcg(FIXED_SEED, 0)
        for _ in range(10):
            assert pcg1.next_uint64() == pcg2.next_uint64()

    def test_is_independent(self):
        """Round N derivation doesn't depend on rounds 0..N-1.

        Calling _derive_round_pcg for round 5 directly must produce the same
        result as deriving round 5 after having derived rounds 0-4.
        """
        # Derive round 5 directly
        pcg_direct = _derive_round_pcg(FIXED_SEED, 5)
        direct_output = pcg_direct.next_uint64()

        # Derive rounds 0 through 4 first (consuming their PCG streams)
        for r in range(5):
            pcg_prior = _derive_round_pcg(FIXED_SEED, r)
            for _ in range(100):
                pcg_prior.next_uint64()

        # Now derive round 5
        pcg_after = _derive_round_pcg(FIXED_SEED, 5)
        after_output = pcg_after.next_uint64()

        assert direct_output == after_output

    def test_different_rounds_different_output(self):
        """Different rounds produce different PCG streams."""
        pcg0 = _derive_round_pcg(FIXED_SEED, 0)
        pcg1 = _derive_round_pcg(FIXED_SEED, 1)
        assert pcg0.next_uint64() != pcg1.next_uint64()

    def test_different_seeds_different_output(self):
        """Different seeds produce different PCG streams."""
        seed2 = "cd" * SEED_BYTES
        pcg1 = _derive_round_pcg(FIXED_SEED, 0)
        pcg2 = _derive_round_pcg(seed2, 0)
        assert pcg1.next_uint64() != pcg2.next_uint64()

    def test_negative_round_raises(self):
        with pytest.raises(ValueError, match=r"\[0, 2\^32\)"):
            _derive_round_pcg(FIXED_SEED, -1)

    def test_round_overflow_raises(self):
        with pytest.raises(ValueError, match=r"\[0, 2\^32\)"):
            _derive_round_pcg(FIXED_SEED, 2**32)

    def test_invalid_seed_raises(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            _derive_round_pcg("short", 0)


class TestBoundedUint64:
    def test_in_range(self):
        """Output is always in [0, bound) for various bounds."""
        pcg = PCG64DXSM(state=42, increment=17)
        for bound in [1, 2, 6, 136, 1000]:
            for _ in range(200):
                val = _bounded_uint64(pcg, bound)
                assert 0 <= val < bound

    def test_bound_of_one(self):
        """Bound of 1 always returns 0."""
        pcg = PCG64DXSM(state=100, increment=200)
        for _ in range(50):
            assert _bounded_uint64(pcg, 1) == 0

    def test_invalid_bound_raises(self):
        pcg = PCG64DXSM(state=1, increment=1)
        with pytest.raises(ValueError, match="positive"):
            _bounded_uint64(pcg, 0)
        with pytest.raises(ValueError, match="positive"):
            _bounded_uint64(pcg, -1)


class TestFisherYatesShuffle:
    def test_permutation_invariants(self):
        """Every shuffle is a valid permutation (no duplicates, no missing tiles)."""
        pcg = PCG64DXSM(state=12345, increment=67890)
        tiles = list(range(TOTAL_WALL_SIZE))
        shuffled = _fisher_yates_shuffle(tiles, pcg)
        assert sorted(shuffled) == list(range(TOTAL_WALL_SIZE))

    def test_does_not_modify_input(self):
        """Shuffling returns a new list, original is unchanged."""
        pcg = PCG64DXSM(state=42, increment=17)
        original = list(range(10))
        original_copy = list(original)
        _fisher_yates_shuffle(original, pcg)
        assert original == original_copy

    def test_empty_list(self):
        """Shuffling an empty list returns an empty list."""
        pcg = PCG64DXSM(state=1, increment=1)
        assert _fisher_yates_shuffle([], pcg) == []

    def test_single_element(self):
        """Shuffling a single-element list returns the same element."""
        pcg = PCG64DXSM(state=1, increment=1)
        assert _fisher_yates_shuffle([42], pcg) == [42]

    def test_deterministic(self):
        """Same PCG state produces the same shuffle."""
        tiles = list(range(20))
        pcg1 = PCG64DXSM(state=555, increment=777)
        pcg2 = PCG64DXSM(state=555, increment=777)
        assert _fisher_yates_shuffle(tiles, pcg1) == _fisher_yates_shuffle(tiles, pcg2)


class TestCreateSeatRng:
    def test_deterministic(self):
        """Same seed produces the same seat order."""
        rng1 = create_seat_rng(FIXED_SEED)
        rng2 = create_seat_rng(FIXED_SEED)
        seats1 = rng1.sample(range(4), 4)
        seats2 = rng2.sample(range(4), 4)
        assert seats1 == seats2

    def test_none_seed(self):
        """None seed returns a working (unseeded) RNG."""
        rng = create_seat_rng(None)
        # Just verify it's functional
        result = rng.sample(range(4), 4)
        assert sorted(result) == [0, 1, 2, 3]

    def test_different_seeds_different_order(self):
        """Different seeds produce different seat orders (with very high probability)."""
        seed2 = "cd" * SEED_BYTES
        rng1 = create_seat_rng(FIXED_SEED)
        rng2 = create_seat_rng(seed2)
        seats1 = rng1.sample(range(4), 4)
        seats2 = rng2.sample(range(4), 4)
        assert seats1 != seats2


class TestRNGVersion:
    def test_is_set(self):
        """RNG_VERSION is a non-empty string."""
        assert isinstance(RNG_VERSION, str)
        assert len(RNG_VERSION) > 0

    def test_contains_algorithm_name(self):
        """RNG_VERSION identifies the algorithm."""
        assert "pcg64dxsm" in RNG_VERSION


class TestPCG64DXSMReferenceVector:
    def test_fixed_seed_round_yields_expected_outputs(self):
        """Fixed seed+round yields exact expected first N outputs (deterministic regression guard).

        Hardcoded reference values detect any change to the derivation,
        domain prefix, hash function, or PCG algorithm.
        """
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
    def test_range(self):
        """Both dice values are in [1, 6] over 1000 iterations."""
        pcg = PCG64DXSM(state=42, increment=17)
        for _ in range(1000):
            die1, die2 = roll_dice(pcg)
            assert 1 <= die1 <= 6
            assert 1 <= die2 <= 6

    def test_deterministic(self):
        """Same PCG state produces the same dice values."""
        pcg1 = PCG64DXSM(state=123, increment=456)
        pcg2 = PCG64DXSM(state=123, increment=456)
        assert roll_dice(pcg1) == roll_dice(pcg2)

    def test_different_states_different_dice(self):
        """Different PCG states produce different dice (with high probability)."""
        pcg1 = PCG64DXSM(state=1, increment=1)
        pcg2 = PCG64DXSM(state=999, increment=999)
        # Collect multiple rolls to ensure variation
        rolls1 = [roll_dice(pcg1) for _ in range(10)]
        rolls2 = [roll_dice(pcg2) for _ in range(10)]
        assert rolls1 != rolls2


class TestGenerateShuffledWallAndDice:
    def test_deterministic(self):
        """Same seed + round produces the same wall and dice."""
        wall1, dice1 = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        wall2, dice2 = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert wall1 == wall2
        assert dice1 == dice2

    def test_valid_wall(self):
        """Returned wall has 136 unique tiles (0-135)."""
        wall, _ = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert len(wall) == TOTAL_WALL_SIZE
        assert sorted(wall) == list(range(TOTAL_WALL_SIZE))

    def test_valid_dice(self):
        """Returned dice are both in [1, 6]."""
        _, dice = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert 1 <= dice[0] <= 6
        assert 1 <= dice[1] <= 6

    def test_different_rounds_different_results(self):
        """Different rounds produce different walls and/or dice."""
        wall1, _dice1 = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        wall2, _dice2 = generate_shuffled_wall_and_dice(FIXED_SEED, 1)
        assert wall1 != wall2

    def test_different_seeds_different_walls(self):
        """Different seeds produce different walls."""
        seed2 = "cd" * SEED_BYTES
        wall1, _ = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        wall2, _ = generate_shuffled_wall_and_dice(seed2, 0)
        assert wall1 != wall2

    def test_wall_is_shuffled(self):
        """Wall is not in sorted order."""
        wall, _ = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert wall != list(range(TOTAL_WALL_SIZE))


class TestDetermineFirstDealer:
    def test_deterministic(self):
        """Same seed produces the same dealer, first dice, and second dice."""
        result1 = determine_first_dealer(FIXED_SEED)
        result2 = determine_first_dealer(FIXED_SEED)
        assert result1 == result2

    def test_dealer_in_range(self):
        """Dealer seat is in [0, 3]."""
        dealer, _, _ = determine_first_dealer(FIXED_SEED)
        assert 0 <= dealer <= 3

    def test_dice_values_valid(self):
        """All dice values are in [1, 6]."""
        _, first_dice, second_dice = determine_first_dealer(FIXED_SEED)
        for die in (*first_dice, *second_dice):
            assert 1 <= die <= 6

    def test_different_seeds_different_dealers(self):
        """Different seeds produce different dealers (with high probability)."""
        dealers = set()
        for i in range(20):
            seed = f"{i:02x}" * SEED_BYTES
            dealer, _, _ = determine_first_dealer(seed)
            dealers.add(dealer)
        assert len(dealers) > 1

    def test_all_seats_reachable(self):
        """Over many seeds, all 4 seats appear as dealer."""
        dealers = set()
        for i in range(200):
            seed = f"{i:02x}" * SEED_BYTES
            dealer, _, _ = determine_first_dealer(seed)
            dealers.add(dealer)
        assert dealers == {0, 1, 2, 3}

    def test_two_roll_procedure(self):
        """Verify the two-roll procedure matches manual calculation."""
        dealer, first_dice, second_dice = determine_first_dealer(FIXED_SEED)
        temp_dealer = (sum(first_dice) - 1) % 4
        expected_dealer = (temp_dealer + sum(second_dice) - 1) % 4
        assert dealer == expected_dealer
