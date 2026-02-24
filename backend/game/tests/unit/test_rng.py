"""
Unit tests for random number generation module.

Covers PCG64DXSM determinism, Fisher-Yates correctness, seed generation,
validation, bounded sampling, and reference vector regression tests.
"""

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
    def test_length_and_valid_hex(self):
        """Seed is 192 hex characters (96 bytes) and decodes correctly."""
        seed = generate_seed()
        assert len(seed) == SEED_BYTES * 2
        decoded = bytes.fromhex(seed)
        assert len(decoded) == SEED_BYTES

    def test_uniqueness(self):
        """Two calls produce different seeds."""
        assert generate_seed() != generate_seed()


class TestValidateSeedHex:
    def test_accepts_valid_seed(self):
        validate_seed_hex(FIXED_SEED)

    def test_accepts_uppercase_hex(self):
        validate_seed_hex(FIXED_SEED.upper())

    def test_rejects_wrong_length(self):
        with pytest.raises(ValueError, match="192 hex characters"):
            validate_seed_hex("ab" * 10)

    def test_rejects_non_hex_characters(self):
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
        pcg_direct = _derive_round_pcg(FIXED_SEED, 5)
        direct_output = pcg_direct.next_uint64()

        for r in range(5):
            pcg_prior = _derive_round_pcg(FIXED_SEED, r)
            for _ in range(100):
                pcg_prior.next_uint64()

        pcg_after = _derive_round_pcg(FIXED_SEED, 5)
        after_output = pcg_after.next_uint64()

        assert direct_output == after_output

    def test_different_rounds_different_output(self):
        """Different rounds produce different PCG streams."""
        pcg0 = _derive_round_pcg(FIXED_SEED, 0)
        pcg1 = _derive_round_pcg(FIXED_SEED, 1)
        assert pcg0.next_uint64() != pcg1.next_uint64()

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

    def test_invalid_bound_raises(self):
        pcg = PCG64DXSM(state=1, increment=1)
        with pytest.raises(ValueError, match=r"bound must be in"):
            _bounded_uint64(pcg, 0)

    def test_bound_exceeding_uint64_raises(self):
        pcg = PCG64DXSM(state=1, increment=1)
        with pytest.raises(ValueError, match=r"bound must be in"):
            _bounded_uint64(pcg, (1 << 64) + 1)

    def test_bound_exactly_uint64_max_succeeds(self):
        pcg = PCG64DXSM(state=42, increment=17)
        result = _bounded_uint64(pcg, 1 << 64)
        assert 0 <= result < (1 << 64)


class TestFisherYatesShuffle:
    def test_permutation_invariants(self):
        """Every shuffle is a valid permutation (no duplicates, no missing tiles)."""
        pcg = PCG64DXSM(state=12345, increment=67890)
        tiles = list(range(NUM_TILES))
        shuffled = _fisher_yates_shuffle(tiles, pcg)
        assert sorted(shuffled) == list(range(NUM_TILES))

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
        """Both dice values are in [1, 6]."""
        pcg = PCG64DXSM(state=42, increment=17)
        for _ in range(100):
            die1, die2 = roll_dice(pcg)
            assert 1 <= die1 <= 6
            assert 1 <= die2 <= 6

    def test_deterministic(self):
        """Same PCG state produces the same dice values."""
        pcg1 = PCG64DXSM(state=123, increment=456)
        pcg2 = PCG64DXSM(state=123, increment=456)
        assert roll_dice(pcg1) == roll_dice(pcg2)


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
        assert len(wall) == NUM_TILES
        assert sorted(wall) == list(range(NUM_TILES))

    def test_valid_dice(self):
        """Returned dice are both in [1, 6]."""
        _, dice = generate_shuffled_wall_and_dice(FIXED_SEED, 0)
        assert 1 <= dice[0] <= 6
        assert 1 <= dice[1] <= 6


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

    def test_two_roll_procedure(self):
        """Verify the two-roll procedure matches manual calculation."""
        dealer, first_dice, second_dice = determine_first_dealer(FIXED_SEED)
        temp_dealer = (sum(first_dice) - 1) % 4
        expected_dealer = (temp_dealer + sum(second_dice) - 1) % 4
        assert dealer == expected_dealer
