from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise, permutations, product
from math import comb
from typing import Any

from game.logic.settings import NUM_PLAYERS
from game.logic.shanten import calculate_shanten
from game.logic.tiles import HONOR_34_START, NUM_TILE_TYPES, NUM_TILES, hand_to_34_array
from scripts.measure_wall.metrics import (
    CellFamily,
    Comparison,
    FamilySummary,
    FractionHistogram,
    MeanStat,
    MeanSummary,
    compare,
    uniform,
    warn_threshold,
)
from scripts.measure_wall.sampling import (
    HAND_SIZE,
    ControlRound,
    GameSample,
    RoundSample,
    StructuralError,
    check_round,
    sample_engine_game,
)

DIE_FACES = 6
DICE_SUM_PROBABILITIES = tuple((DIE_FACES - abs(total - 7)) / 36 for total in range(2, 13))
RED_FIVES = frozenset((16, 52, 88))
HONOR_TILES = (NUM_TILE_TYPES - HONOR_34_START) * 4
COPIES_PER_TYPE = 4
SHANTEN_MAX = 6
SHANTEN_13_LABELS = tuple(str(value) for value in range(SHANTEN_MAX + 1))
SHANTEN_14_LABELS = tuple(str(value) for value in range(-1, SHANTEN_MAX + 1))
SEAT_PERMUTATIONS = {seats: index for index, seats in enumerate(permutations(range(NUM_PLAYERS)))}


def first_dealer_probabilities() -> tuple[float, ...]:
    """
    The exact seat probabilities of the two-roll rule, enumerated over the 1296 ordered roll pairs.

    Provisional East's roll picks the temporary dealer by its sum, and that seat's roll picks the first dealer the same
    way, so the seats are not equally likely: 326, 324, 322 and 324 out of 1296.
    """
    counts = [0.0] * NUM_PLAYERS
    for first, second in product(range(2, 13), repeat=2):
        weight = DICE_SUM_PROBABILITIES[first - 2] * DICE_SUM_PROBABILITIES[second - 2]
        temporary = (first - 1) % NUM_PLAYERS
        counts[(temporary + second - 1) % NUM_PLAYERS] += weight

    return tuple(counts)


def _seat_shanten_stats() -> list[MeanStat]:
    return [MeanStat(f"mean shanten of 13-tile hands, seat {offset} after the dealer") for offset in range(NUM_PLAYERS)]


@dataclass
class GameAccumulator:
    """
    One game's observations, folded into the per-game means when the game ends.
    """

    adjacent: list[int] = field(default_factory=list)
    pairs: list[int] = field(default_factory=list)
    honors: list[int] = field(default_factory=list)
    reds: list[int] = field(default_factory=list)
    shanten_13: list[int] = field(default_factory=list)
    shanten_14: list[int] = field(default_factory=list)
    seat_shanten: list[list[int]] = field(default_factory=lambda: [[] for _ in range(NUM_PLAYERS)])
    same_id: list[int] = field(default_factory=list)
    same_type: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class Report:
    """
    Everything a run measured, ready for the text and JSON renderers.
    """

    metadata: dict[str, Any]
    errors: list[str]
    games: int
    walls: int
    consecutive_pairs: int
    identical_walls: int
    families: list[FamilySummary]
    means: list[MeanSummary]
    comparisons: list[Comparison]
    control_method: str


class Measurement:
    """
    Fold engine and control samples into the cell families, per-game means and histograms the report shows.
    """

    def __init__(self) -> None:
        self.games = 0
        self.walls = 0
        self.consecutive_pairs = 0
        self.identical_walls = 0
        self.errors: list[str] = []
        self.tile_by_position = CellFamily("tile id by wall position", uniform(NUM_TILES), rows=NUM_TILES)
        self.type_by_position = CellFamily("tile type by wall position", uniform(NUM_TILE_TYPES), rows=NUM_TILES)
        self.dealt_type_by_seat = CellFamily(
            "tile type among the dealt 13, by seat after the dealer",
            uniform(NUM_TILE_TYPES),
            rows=NUM_PLAYERS,
            variance_factor=(NUM_TILES - HAND_SIZE) / (NUM_TILES - 1),
        )
        self.dora_type = CellFamily("first dora indicator type", uniform(NUM_TILE_TYPES))
        self.break_faces = CellFamily("wall-break dice faces, by die", uniform(DIE_FACES), rows=2)
        self.break_pairs = CellFamily("wall-break dice ordered pairs", uniform(DIE_FACES * DIE_FACES))
        self.break_sums = CellFamily("wall-break dice sum (triangular)", DICE_SUM_PROBABILITIES)
        self.dealer_faces = CellFamily("first-dealer dice faces, by roll and die", uniform(DIE_FACES), rows=4)
        self.first_dealer = CellFamily("first dealer seat (two-roll rule)", first_dealer_probabilities())
        self.dealer_input_index = CellFamily("first dealer among the input players", uniform(NUM_PLAYERS))
        self.seat_permutation = CellFamily("seat permutation", uniform(len(SEAT_PERMUTATIONS)))
        self.adjacent_types = MeanStat("adjacent equal types per wall", expected=3.0)
        self.hand_pairs = MeanStat(
            "equal-type pairs per 13-tile hand",
            expected=comb(HAND_SIZE, 2) * (COPIES_PER_TYPE - 1) / (NUM_TILES - 1),
        )
        self.hand_honors = MeanStat("honors per 13-tile hand", expected=HAND_SIZE * HONOR_TILES / NUM_TILES)
        self.hand_reds = MeanStat("red fives per 13-tile hand", expected=HAND_SIZE * len(RED_FIVES) / NUM_TILES)
        self.same_id_next_round = MeanStat("positions holding the same tile id in consecutive rounds", expected=1.0)
        self.same_type_next_round = MeanStat(
            "positions holding the same tile type in consecutive rounds",
            expected=NUM_TILES / NUM_TILE_TYPES,
        )
        self.engine_shanten_13 = FractionHistogram("shanten of 13-tile hands", SHANTEN_13_LABELS)
        self.engine_shanten_14 = FractionHistogram("shanten of the dealer's 14 tiles", SHANTEN_14_LABELS)
        self.control_shanten_13 = FractionHistogram("shanten of 13-tile hands", SHANTEN_13_LABELS)
        self.control_shanten_14 = FractionHistogram("shanten of the dealer's 14 tiles", SHANTEN_14_LABELS)
        self.engine_seat_shanten = _seat_shanten_stats()
        self.control_seat_shanten = _seat_shanten_stats()

    def observe_engine(self, game: GameSample) -> None:
        """
        Fold one engine game in; a round that fails a structural check is recorded as an error and skipped.
        """
        self.games += 1
        self._observe_seating(game)
        accumulator = GameAccumulator()
        for sample in game.rounds:
            try:
                check_round(sample)
            except StructuralError as error:
                self.errors.append(f"seed {game.seed[:16]}..., {error}")
                continue

            self.walls += 1
            self._observe_positions(sample, accumulator)
            self._observe_hands(sample, accumulator)
            self._observe_dice(sample)

        self._observe_consecutive_rounds(game, accumulator)
        self._fold(accumulator)

    def observe_control(self, rounds: list[ControlRound]) -> None:
        """
        Fold one game's worth of control deals in.
        """
        by_seat = [
            [calculate_shanten(hand_to_34_array(sample.hands[seat])) for sample in rounds]
            for seat in range(NUM_PLAYERS)
        ]
        shanten_14 = [calculate_shanten(hand_to_34_array(sample.dealer_hand)) for sample in rounds]
        self.control_shanten_13.add_game([value for values in by_seat for value in values], offset=0)
        self.control_shanten_14.add_game(shanten_14, offset=1)
        for stat, values in zip(self.control_seat_shanten, by_seat, strict=True):
            stat.add(sum(values) / len(values))

    def verify_regeneration(self, game: GameSample) -> None:
        """
        Regenerate a game from its seed and record an error unless every seed-derived value comes out the same.
        """
        if sample_engine_game(game.seed, len(game.rounds)) != game:
            self.errors.append(f"seed {game.seed[:16]}... regenerated differently")

    def report(self, metadata: dict[str, Any], control_method: str) -> Report:
        """
        Summarize every accumulator.
        """
        means = [
            self.adjacent_types,
            self.hand_pairs,
            self.hand_honors,
            self.hand_reds,
            self.same_id_next_round,
            self.same_type_next_round,
        ]
        return Report(
            metadata=metadata,
            errors=list(self.errors),
            games=self.games,
            walls=self.walls,
            consecutive_pairs=self.consecutive_pairs,
            identical_walls=self.identical_walls,
            families=[family.summary() for family in self._families()],
            means=[stat.summary() for stat in means],
            comparisons=self._comparisons(),
            control_method=control_method,
        )

    def family_json(self) -> list[dict[str, Any]]:
        """
        The raw counts of every cell family.
        """
        return [family.to_json() for family in self._families()]

    def _families(self) -> list[CellFamily]:
        return [
            self.tile_by_position,
            self.type_by_position,
            self.dealt_type_by_seat,
            self.dora_type,
            self.break_faces,
            self.break_pairs,
            self.break_sums,
            self.dealer_faces,
            self.first_dealer,
            self.dealer_input_index,
            self.seat_permutation,
        ]

    def _comparisons(self) -> list[Comparison]:
        pairs = [
            (self.engine_shanten_13, self.control_shanten_13),
            (self.engine_shanten_14, self.control_shanten_14),
        ]
        comparisons = []
        for engine, control in pairs:
            engine_summaries, control_summaries = engine.summaries(), control.summaries()
            threshold = warn_threshold(len(engine_summaries))
            comparisons.extend(
                compare(left, right, threshold) for left, right in zip(engine_summaries, control_summaries, strict=True)
            )

        threshold = warn_threshold(NUM_PLAYERS)
        comparisons.extend(
            compare(engine.summary(), control.summary(), threshold)
            for engine, control in zip(self.engine_seat_shanten, self.control_seat_shanten, strict=True)
        )
        return comparisons

    def _observe_seating(self, game: GameSample) -> None:
        self.seat_permutation.add(0, SEAT_PERMUTATIONS[game.seats])
        self.seat_permutation.trials += 1
        self.first_dealer.add(0, game.first_dealer)
        self.first_dealer.trials += 1
        self.dealer_input_index.add(0, game.seats.index(game.first_dealer))
        self.dealer_input_index.trials += 1
        for row, face in enumerate((*game.first_roll, *game.second_roll)):
            self.dealer_faces.add(row, face - 1)

        self.dealer_faces.trials += 1

    def _observe_positions(self, sample: RoundSample, accumulator: GameAccumulator) -> None:
        tile_counts = self.tile_by_position.counts
        type_counts = self.type_by_position.counts
        for position, tile in enumerate(sample.permutation):
            tile_counts[position][tile] += 1
            type_counts[position][tile // COPIES_PER_TYPE] += 1

        self.tile_by_position.trials += 1
        self.type_by_position.trials += 1
        types = [tile // COPIES_PER_TYPE for tile in sample.permutation]
        accumulator.adjacent.append(sum(1 for left, right in pairwise(types) if left == right))

    def _observe_hands(self, sample: RoundSample, accumulator: GameAccumulator) -> None:
        for offset in range(NUM_PLAYERS):
            hand = sample.hand_at_offset(offset)
            counts_34 = hand_to_34_array(hand)
            for tile_type, count in enumerate(counts_34):
                self.dealt_type_by_seat.counts[offset][tile_type] += count

            accumulator.pairs.append(sum(comb(count, 2) for count in counts_34))
            accumulator.honors.append(sum(counts_34[HONOR_34_START:]))
            accumulator.reds.append(sum(1 for tile in hand if tile in RED_FIVES))
            shanten = self._shanten(counts_34, lowest=0)
            accumulator.shanten_13.append(shanten)
            accumulator.seat_shanten[offset].append(shanten)

        self.dealt_type_by_seat.trials += HAND_SIZE
        accumulator.shanten_14.append(self._shanten(hand_to_34_array(sample.dealer_hand), lowest=-1))
        self.dora_type.add(0, sample.wall.dora_indicators[0] // COPIES_PER_TYPE)
        self.dora_type.trials += 1

    def _observe_dice(self, sample: RoundSample) -> None:
        first, second = sample.dice
        self.break_faces.add(0, first - 1)
        self.break_faces.add(1, second - 1)
        self.break_faces.trials += 1
        self.break_pairs.add(0, (first - 1) * DIE_FACES + (second - 1))
        self.break_pairs.trials += 1
        self.break_sums.add(0, first + second - 2)
        self.break_sums.trials += 1

    def _observe_consecutive_rounds(self, game: GameSample, accumulator: GameAccumulator) -> None:
        for earlier, later in pairwise(game.rounds):
            self.consecutive_pairs += 1
            same_id = sum(1 for a, b in zip(earlier.permutation, later.permutation, strict=True) if a == b)
            same_type = sum(
                1
                for a, b in zip(earlier.permutation, later.permutation, strict=True)
                if a // COPIES_PER_TYPE == b // COPIES_PER_TYPE
            )
            accumulator.same_id.append(same_id)
            accumulator.same_type.append(same_type)
            if earlier.permutation == later.permutation:
                self.identical_walls += 1

    def _fold(self, accumulator: GameAccumulator) -> None:
        for stat, values in (
            (self.adjacent_types, accumulator.adjacent),
            (self.hand_pairs, accumulator.pairs),
            (self.hand_honors, accumulator.honors),
            (self.hand_reds, accumulator.reds),
            (self.same_id_next_round, accumulator.same_id),
            (self.same_type_next_round, accumulator.same_type),
        ):
            if values:
                stat.add(sum(values) / len(values))

        if accumulator.shanten_13:
            self.engine_shanten_13.add_game(accumulator.shanten_13, offset=0)
            self.engine_shanten_14.add_game(accumulator.shanten_14, offset=1)
            for stat, values in zip(self.engine_seat_shanten, accumulator.seat_shanten, strict=True):
                stat.add(sum(values) / len(values))

    @staticmethod
    def _shanten(counts_34: list[int], lowest: int) -> int:
        shanten = calculate_shanten(counts_34)
        if not (lowest <= shanten <= SHANTEN_MAX):
            raise StructuralError(f"shanten {shanten} outside [{lowest}, {SHANTEN_MAX}]")

        return shanten
