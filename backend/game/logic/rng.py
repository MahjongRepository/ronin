"""
Random number generation for wall shuffling and dealer determination.

Uses PCG64DXSM (Permuted Congruential Generator with DXSM output function):
1. Generate a cryptographic seed (96 bytes / 768 bits) via secrets module
2. Derive per-round RNG state via SHA512 with domain separation (versioned prefix)
3. Use PCG64DXSM to generate high-quality random uint64 values
4. Apply Fisher-Yates shuffle with rejection sampling for a provably unbiased permutation

PCG64DXSM was chosen over MT19937 because:
- Passes all BigCrush/PractRand statistical tests
- 128-bit state (vs 2.5KB for MT19937)
- DXSM output has excellent avalanche properties (no SHA512 post-processing needed)
- Industry standard: default bit generator in NumPy since v1.22

Reference: O'Neill, M. (2014). "PCG: A Family of Simple Fast Space-Efficient
Statistically Good Algorithms for Random Number Generation."
"""

import hashlib
import random
import secrets

SEED_BYTES = 96  # 768 bits — exceeds 136!/(4!)^34 ≈ 2^616 unique game space (136! ≈ 2^772.5)
TOTAL_WALL_SIZE = 136
RNG_VERSION = "pcg64dxsm-v1"  # Stored in game metadata for replay compatibility detection
_DOMAIN_PREFIX = b"ronin-wall-v1:"  # Domain separator for hash-based derivation (versioned)
_DEALER_DOMAIN_PREFIX = b"ronin-dealer-v1:"  # Domain separator for dealer determination

# PCG64DXSM constants
# Full 128-bit LCG multiplier (canonical, passes all BigCrush/PractRand tests)
_PCG_MULTIPLIER = 0x2360ED051FC65DA44385DF649FCCF645
_PCG_DXSM_MUL = 0xDA942042E4DD58B5  # DXSM output permutation multiplier
_UINT128_MASK = (1 << 128) - 1
_UINT64_MASK = (1 << 64) - 1


def validate_seed_hex(seed_hex: str) -> None:
    """Validate that a seed string is the correct hex format.

    Enforces exact length (192 hex chars = 96 bytes = 768 bits) and valid hex characters.
    Raises TypeError for non-string input, ValueError for invalid format.
    """
    if not isinstance(seed_hex, str):
        raise TypeError(f"Seed must be a string, got {type(seed_hex).__name__}")
    expected_length = SEED_BYTES * 2
    if len(seed_hex) != expected_length:
        raise ValueError(f"Seed must be exactly {expected_length} hex characters, got {len(seed_hex)}")
    try:
        bytes.fromhex(seed_hex)
    except ValueError:
        raise ValueError("Seed contains invalid hex characters") from None


class PCG64DXSM:
    """
    Pure Python PCG64DXSM (Permuted Congruential Generator).

    Uses a 128-bit LCG state with the full 128-bit multiplier and the DXSM
    (double-xorshift-multiply) output permutation for high-quality 64-bit output.

    Reference: NumPy's default PCG64DXSM bit generator uses the same constants.
    """

    def __init__(self, state: int, increment: int) -> None:
        self._inc = ((increment << 1) | 1) & _UINT128_MASK  # increment must be odd
        # Initialization: seed injection + two LCG advances to avoid weak initial states.
        # Note: this differs from NumPy's PCG64DXSM init (which advances from 0 before
        # adding the seed). The difference is immaterial since inputs come from SHA-512.
        self._state = (state + self._inc) & _UINT128_MASK  # seed injection
        self._state = (self._state * _PCG_MULTIPLIER + self._inc) & _UINT128_MASK  # advance 1
        self._state = (self._state * _PCG_MULTIPLIER + self._inc) & _UINT128_MASK  # advance 2

    def next_uint64(self) -> int:
        """Generate the next 64-bit unsigned integer and advance state."""
        # Output from current state (output before advance)
        state = self._state
        hi = (state >> 64) & _UINT64_MASK
        lo = state & _UINT64_MASK
        lo = lo | 1  # force odd for multiplication

        # DXSM output permutation
        hi ^= hi >> 32
        hi = (hi * _PCG_DXSM_MUL) & _UINT64_MASK
        hi ^= hi >> 48
        hi = (hi * lo) & _UINT64_MASK

        # Advance state (128-bit LCG)
        self._state = (state * _PCG_MULTIPLIER + self._inc) & _UINT128_MASK

        return hi


def generate_seed() -> str:
    """Generate a cryptographic seed as a hex string (192 chars / 768 bits)."""
    return secrets.token_bytes(SEED_BYTES).hex()


def _derive_pcg(domain_prefix: bytes, data: bytes) -> PCG64DXSM:
    """
    Derive a PCG64DXSM from SHA512 hash of domain-separated data.

    SHA512(domain_prefix + data) produces 64 bytes; the first 16 bytes
    become the PCG state and the next 16 bytes become the increment.
    Domain separation ensures different contexts produce different output.
    """
    derived = hashlib.sha512(domain_prefix + data).digest()
    state = int.from_bytes(derived[:16], byteorder="little")
    increment = int.from_bytes(derived[16:32], byteorder="little")
    return PCG64DXSM(state, increment)


def _derive_round_pcg(seed_hex: str, round_number: int) -> PCG64DXSM:
    """
    Derive a per-round PCG64DXSM from the game seed.

    Uses hash-based derivation with domain separation:
    SHA512(_DOMAIN_PREFIX + seed_bytes + round_number_bytes).
    This is O(1) regardless of round number.
    """
    if not (0 <= round_number < 2**32):
        raise ValueError("round_number must be in [0, 2^32)")
    validate_seed_hex(seed_hex)
    seed_bytes = bytes.fromhex(seed_hex)
    round_bytes = round_number.to_bytes(4, byteorder="little")
    return _derive_pcg(_DOMAIN_PREFIX, seed_bytes + round_bytes)


def _bounded_uint64(pcg: PCG64DXSM, bound: int) -> int:
    """
    Generate an unbiased random integer in [0, bound) via rejection sampling.

    Rejects values from the partial final bucket to eliminate modulo bias entirely.
    With 64-bit output and max bound of 136, rejection probability per step is
    ~136/2^64 ≈ 7.4x10^-18 — effectively zero overhead in practice.
    """
    if bound <= 0 or bound > (1 << 64):
        raise ValueError("bound must be in (0, 2^64]")
    limit = (1 << 64) - ((1 << 64) % bound)
    while True:
        r = pcg.next_uint64()
        if r < limit:
            return r % bound


def _fisher_yates_shuffle(tiles: list[int], pcg: PCG64DXSM) -> list[int]:
    """
    Perform Fisher-Yates (Knuth) shuffle using PCG64DXSM random values.

    For i in 0..n-2: swap tiles[i] with tiles[i + bounded_uint64(n - i)]

    Uses rejection sampling via _bounded_uint64 to produce a provably unbiased
    permutation. This follows the RNG research recommendation and industry best
    practice (Node.js crypto.randomInt and NumPy both use rejection sampling).
    """
    n = len(tiles)
    result = list(tiles)
    for i in range(n - 1):
        j = i + _bounded_uint64(pcg, n - i)
        result[i], result[j] = result[j], result[i]
    return result


def roll_dice(pcg: PCG64DXSM) -> tuple[int, int]:
    """Roll two standard six-sided dice using the PCG generator."""
    die1 = _bounded_uint64(pcg, 6) + 1
    die2 = _bounded_uint64(pcg, 6) + 1
    return die1, die2


def generate_shuffled_wall_and_dice(seed_hex: str, round_number: int) -> tuple[list[int], tuple[int, int]]:
    """
    Generate a shuffled wall and roll dice for wall breaking.

    Order matches physical Mahjong: tiles are shuffled (wall built) first,
    then dice are rolled. Both operations consume from the same deterministic
    PCG stream, so the dice values are fully determined by the seed and round.
    """
    pcg = _derive_round_pcg(seed_hex, round_number)
    tiles = list(range(TOTAL_WALL_SIZE))
    shuffled = _fisher_yates_shuffle(tiles, pcg)
    dice = roll_dice(pcg)
    return shuffled, dice


def _derive_dealer_pcg(seed_hex: str) -> PCG64DXSM:
    """
    Derive a PCG64DXSM for dealer determination from the game seed.

    Uses a separate domain prefix ("ronin-dealer-v1:") so the dealer RNG stream
    is independent from the wall RNG stream.
    """
    validate_seed_hex(seed_hex)
    return _derive_pcg(_DEALER_DOMAIN_PREFIX, bytes.fromhex(seed_hex))


def determine_first_dealer(seed_hex: str) -> tuple[int, tuple[int, int], tuple[int, int]]:
    """
    Determine the first dealer using the two-dice-roll method (二度振り).

    Simulate the real Japanese mahjong procedure:
    1. Provisional East (seat 0) rolls two dice -> determine temporary dealer
    2. Temporary dealer rolls two dice -> determine actual first dealer

    Use a dedicated PCG stream derived from the game seed (separate from wall RNG).

    The two-roll method nearly eliminates the single-roll bias:
    - Single roll: 22.2% / 25.0% / 27.8% / 25.0% (seat 0/1/2/3)
    - Two rolls: ~25.15% / 25.00% / 24.85% / 25.00% (<=0.15% residual bias)

    Return (dealer_seat, first_dice, second_dice).
    """
    pcg = _derive_dealer_pcg(seed_hex)
    first_dice = roll_dice(pcg)
    temp_dealer = (sum(first_dice) - 1) % 4
    second_dice = roll_dice(pcg)
    dealer = (temp_dealer + sum(second_dice) - 1) % 4
    return dealer, first_dice, second_dice


def create_seat_rng(seed_hex: str | None) -> random.Random:
    """
    Create a seeded RNG for seat assignment (matchmaker).

    Uses stdlib random.Random for seat shuffling — statistical perfection
    is not critical for 4-seat assignment, and this avoids coupling the
    matchmaker to PCG64DXSM internals.
    """
    if seed_hex is None:
        return random.Random()  # noqa: S311
    validate_seed_hex(seed_hex)
    return random.Random(int(seed_hex, 16))  # noqa: S311
