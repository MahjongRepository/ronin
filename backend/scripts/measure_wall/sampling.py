from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.logic.rng import SEED_BYTES, determine_first_dealer, generate_shuffled_wall_and_dice, seat_permutation
from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import NUM_TILES
from game.logic.wall import Wall, build_wall, deal_initial_hands

if TYPE_CHECKING:
    from collections.abc import Iterator

HAND_SIZE = 13
DEALT_TILES = NUM_PLAYERS * HAND_SIZE
ALL_TILES = frozenset(range(NUM_TILES))
CONTROL_METHOD = "random.Random(experiment seed).shuffle, hands cut from the front of the permutation"


class StructuralError(Exception):
    """
    A sample violates an invariant every wall must satisfy, which is a fault, never a statistical fluctuation.
    """


@dataclass(frozen=True)
class RoundSample:
    """
    One round as the engine produced it: the raw permutation, its dice, the wall built from them and the deal.
    """

    round_number: int
    dealer_seat: int
    permutation: tuple[int, ...]
    dice: tuple[int, int]
    wall: Wall
    hands: tuple[tuple[int, ...], ...]
    dealer_draw: int

    @property
    def dealer_hand(self) -> tuple[int, ...]:
        """
        The dealer's 14 tiles: the dealt 13 and the first draw.
        """
        return (*self.hands[self.dealer_seat], self.dealer_draw)

    def hand_at_offset(self, offset: int) -> tuple[int, ...]:
        """
        The 13-tile hand of the seat `offset` places after the dealer.
        """
        return self.hands[(self.dealer_seat + offset) % NUM_PLAYERS]


@dataclass(frozen=True)
class GameSample:
    """
    One game's seed-derived facts and its rounds.
    """

    seed: str
    seats: tuple[int, ...]
    first_dealer: int
    first_roll: tuple[int, int]
    second_roll: tuple[int, int]
    rounds: tuple[RoundSample, ...]


@dataclass(frozen=True)
class ControlRound:
    """
    One round's starting hands dealt by the control shuffle.
    """

    hands: tuple[tuple[int, ...], ...]
    dealer_hand: tuple[int, ...]


def build_round_sample(
    *,
    round_number: int,
    dealer_seat: int,
    permutation: tuple[int, ...],
    dice: tuple[int, int],
) -> RoundSample:
    """
    Run a permutation and its dice through the engine's wall split and deal.
    """
    wall = build_wall(list(permutation), dice, dealer_seat)
    dealt, hands = deal_initial_hands(wall, dealer_seat)
    return RoundSample(
        round_number=round_number,
        dealer_seat=dealer_seat,
        permutation=permutation,
        dice=dice,
        wall=wall,
        hands=tuple(tuple(hand) for hand in hands),
        dealer_draw=dealt.live_tiles[0],
    )


def sample_engine_game(seed: str, rounds: int) -> GameSample:
    """
    Sample a game from its seed: the seat permutation, the first dealer and `rounds` walls with the dealer rotating.
    """
    first_dealer, first_roll, second_roll = determine_first_dealer(seed)
    samples = []
    for round_number in range(rounds):
        permutation, dice = generate_shuffled_wall_and_dice(seed, round_number)
        sample = build_round_sample(
            round_number=round_number,
            dealer_seat=(first_dealer + round_number) % NUM_PLAYERS,
            permutation=tuple(permutation),
            dice=dice,
        )
        samples.append(sample)

    return GameSample(
        seed=seed,
        seats=seat_permutation(seed),
        first_dealer=first_dealer,
        first_roll=first_roll,
        second_roll=second_roll,
        rounds=tuple(samples),
    )


def check_round(sample: RoundSample) -> None:
    """
    Raise StructuralError unless the permutation, the wall and the deal each own every tile exactly once.
    """
    where = f"round {sample.round_number}"
    if sorted(sample.permutation) != list(range(NUM_TILES)):
        raise StructuralError(f"{where}: the permutation is not the 136 tile ids")

    wall_tiles = (*sample.wall.live_tiles, *sample.wall.dead_wall.tiles)
    if len(wall_tiles) != NUM_TILES or set(wall_tiles) != ALL_TILES:
        raise StructuralError(f"{where}: the live and dead walls do not own every tile once")

    dealt = [tile for hand in sample.hands for tile in hand]
    if any(len(hand) != HAND_SIZE for hand in sample.hands) or len(sample.hands) != NUM_PLAYERS:
        raise StructuralError(f"{where}: the deal is not {NUM_PLAYERS} hands of {HAND_SIZE}")

    front = sample.wall.live_tiles[:DEALT_TILES]
    if sorted(dealt) != sorted(front) or sample.dealer_draw != sample.wall.live_tiles[DEALT_TILES]:
        raise StructuralError(f"{where}: the hands and the dealer's draw are not the front of the live wall")


def engine_seeds(experiment_seed: int, games: int) -> Iterator[str]:
    """
    Yield `games` engine seeds of the production size from a stream fixed by the experiment seed.
    """
    stream = random.Random(f"ronin-measure-wall-engine-{experiment_seed}")  # noqa: S311
    for _ in range(games):
        yield stream.randbytes(SEED_BYTES).hex()


def control_rounds(experiment_seed: int, count: int) -> Iterator[ControlRound]:
    """
    Yield `count` control deals from the stdlib shuffle, independent of every engine function.
    """
    stream = random.Random(f"ronin-measure-wall-control-{experiment_seed}")  # noqa: S311
    for _ in range(count):
        tiles = list(range(NUM_TILES))
        stream.shuffle(tiles)
        hands = tuple(tuple(tiles[seat * HAND_SIZE : (seat + 1) * HAND_SIZE]) for seat in range(NUM_PLAYERS))
        yield ControlRound(hands=hands, dealer_hand=(*hands[0], tiles[DEALT_TILES]))
