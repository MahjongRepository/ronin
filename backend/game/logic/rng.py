import hashlib
import random
import secrets
import string
from typing import Protocol

from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import NUM_TILES

SEED_BYTES = 96
RNG_VERSION = "shake256-v1"
_WALL_DOMAIN = b"ronin-wall-shake256-v1:"
_DEALER_DOMAIN = b"ronin-dealer-shake256-v1:"
_WORD_BYTES = 8
_INITIAL_WORDS = 160
_UINT64_BOUND = 1 << 64


def validate_seed_hex(seed_hex: str) -> None:
    """Validate that a seed string is the correct hex format.

    Enforces exact length (192 hex chars = 96 bytes = 768 bits) and that every character is a hex digit; whitespace is
    rejected even though bytes.fromhex would skip it. Raises TypeError for non-string input, ValueError for invalid
    format.
    """
    if not isinstance(seed_hex, str):
        raise TypeError(f"Seed must be a string, got {type(seed_hex).__name__}")

    expected_length = SEED_BYTES * 2
    if len(seed_hex) != expected_length:
        raise ValueError(f"Seed must be exactly {expected_length} hex characters, got {len(seed_hex)}")

    if any(char not in string.hexdigits for char in seed_hex):
        raise ValueError("Seed contains invalid hex characters")


class WordSource(Protocol):
    """
    Anything that yields 64-bit words; the sampling functions take this so tests can script exact words.
    """

    def next_uint64(self) -> int: ...


class WordStream:
    """
    Deterministic stream of 64-bit words read from SHAKE256(domain || data).

    SHAKE256 is an extendable-output function: a longer digest of the same input starts with the shorter one, so the
    stream keeps a cursor into the digest prefix read so far and doubles the prefix when the cursor runs past it; the
    first prefix covers a whole wall (135 shuffle words and two dice), so a refill follows only a rejection. Given
    a secret, uniformly random seed, no output word is predictable from the others, which is why the game seed is
    never shared during a game.
    """

    def __init__(self, domain: bytes, data: bytes) -> None:
        self._xof = hashlib.shake_256(domain + data)
        self._buffer = self._xof.digest(_INITIAL_WORDS * _WORD_BYTES)
        self._cursor = 0

    def next_uint64(self) -> int:
        """
        Return the next 64-bit word, little-endian, extending the digest prefix when it is exhausted.
        """
        end = self._cursor + _WORD_BYTES
        if end > len(self._buffer):
            self._buffer = self._xof.digest(2 * len(self._buffer))

        word = int.from_bytes(self._buffer[self._cursor : end], byteorder="little")
        self._cursor = end
        return word


def generate_seed() -> str:
    """
    Generate a cryptographic seed as a hex string (192 chars / 768 bits).
    """
    return secrets.token_bytes(SEED_BYTES).hex()


def _round_stream(seed_hex: str, round_number: int) -> WordStream:
    """
    Derive the word stream for one round: SHAKE256(wall domain || seed || round as 4 little-endian bytes).
    """
    if not (0 <= round_number < 2**32):
        raise ValueError("round_number must be in [0, 2^32)")

    validate_seed_hex(seed_hex)
    return WordStream(_WALL_DOMAIN, bytes.fromhex(seed_hex) + round_number.to_bytes(4, byteorder="little"))


def bounded_uint(words: WordSource, bound: int) -> int:
    """
    Return a uniform integer in [0, bound) by rejection sampling, so there is no modulo bias.

    A word from the partial final bucket is rejected and the next one read; with bound <= 136 that happens with
    probability ~136/2^64 per word.
    """
    if bound <= 0 or bound > _UINT64_BOUND:
        raise ValueError("bound must be in (0, 2^64]")

    limit = _UINT64_BOUND - (_UINT64_BOUND % bound)
    while True:
        word = words.next_uint64()
        if word < limit:
            return word % bound


def fisher_yates_shuffle(tiles: list[int], words: WordSource) -> list[int]:
    """
    Return a uniformly random permutation of tiles (Fisher-Yates, forward form).

    For i in 0..n-2, swap position i with a uniform position in [i, n); given uniform words every permutation is equally
    likely.
    """
    n = len(tiles)
    result = list(tiles)
    for i in range(n - 1):
        j = i + bounded_uint(words, n - i)
        result[i], result[j] = result[j], result[i]

    return result


def roll_dice(words: WordSource) -> tuple[int, int]:
    """
    Roll two standard six-sided dice.
    """
    return bounded_uint(words, 6) + 1, bounded_uint(words, 6) + 1


def generate_shuffled_wall_and_dice(seed_hex: str, round_number: int) -> tuple[list[int], tuple[int, int]]:
    """
    Shuffle the 136 tiles and roll the wall-break dice for one round.

    Order matches physical Mahjong: the wall is built first, then the dice are rolled, both from the round's stream.
    """
    words = _round_stream(seed_hex, round_number)
    shuffled = fisher_yates_shuffle(list(range(NUM_TILES)), words)
    return shuffled, roll_dice(words)


def determine_first_dealer(seed_hex: str) -> tuple[int, tuple[int, int], tuple[int, int]]:
    """
    Determine the first dealer using the two-dice-roll method (二度振り).

    Simulate the real Japanese mahjong procedure:
    1. Provisional East (seat 0) rolls two dice -> determine temporary dealer
    2. Temporary dealer rolls two dice -> determine actual first dealer

    Use a dedicated stream derived from the game seed (separate domain from the wall stream).

    The two-roll method nearly eliminates the single-roll bias:
    - Single roll: 22.2% / 25.0% / 27.8% / 25.0% (seat 0/1/2/3)
    - Two rolls: ~25.15% / 25.00% / 24.85% / 25.00% (<=0.15% residual bias)

    Return (dealer_seat, first_dice, second_dice).
    """
    validate_seed_hex(seed_hex)
    words = WordStream(_DEALER_DOMAIN, bytes.fromhex(seed_hex))

    first_dice = roll_dice(words)
    temp_dealer = (sum(first_dice) - 1) % NUM_PLAYERS

    second_dice = roll_dice(words)
    dealer = (temp_dealer + sum(second_dice) - 1) % NUM_PLAYERS
    return dealer, first_dice, second_dice


def create_seat_rng(seed_hex: str | None) -> random.Random:
    """
    Create a seeded RNG for seat assignment (matchmaker).

    Uses stdlib random.Random for seat shuffling — statistical perfection is not critical for 4-seat assignment, and
    this keeps the matchmaker off the wall stream.
    """
    if seed_hex is None:
        return random.Random()  # noqa: S311

    validate_seed_hex(seed_hex)
    return random.Random(int(seed_hex, 16))  # noqa: S311
