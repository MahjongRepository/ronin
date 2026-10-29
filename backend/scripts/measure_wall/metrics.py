from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

FAMILY_ALARM_RATE = 1e-3
MIN_EXPECTED_PER_CELL = 10.0
MIN_CLUSTERS = 30
MIN_EVENTS = 20
EXACT_TAIL_FROM_Z = 2.5
TAIL_TERM_CUTOFF = 1e-18


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    DEGENERATE = "degenerate"
    INSUFFICIENT = "insufficient"


WARNING_STATUSES = frozenset((Status.WARN, Status.DEGENERATE))


def two_sided_tail(z: float) -> float:
    """
    Return the probability that a standard normal deviates from zero by more than |z|.
    """
    return math.erfc(abs(z) / math.sqrt(2))


def warn_threshold(cells: int) -> float:
    """
    Return the |z| whose two-sided normal tail, summed over `cells` (a union bound), equals the family alarm rate.
    """
    target = FAMILY_ALARM_RATE / cells
    low, high = 0.0, 20.0
    for _ in range(64):
        mid = (low + high) / 2
        if two_sided_tail(mid) > target:
            low = mid
        else:
            high = mid

    return high


def binomial_two_sided_tail(trials: int, probability: float, count: int) -> float:
    """
    Return twice the smaller exact one-sided tail of Binomial(trials, probability) at `count`, capped at 1.

    The normal approximation understates the far tails of a skewed binomial, so a family's verdict uses this exact tail;
    the terms are summed outward from `count` by the pmf recurrence until they stop mattering.
    """
    if trials == 0 or not 0 < probability < 1:
        return 1.0

    log_pmf = (
        math.lgamma(trials + 1)
        - math.lgamma(count + 1)
        - math.lgamma(trials - count + 1)
        + count * math.log(probability)
        + (trials - count) * math.log1p(-probability)
    )
    term = total = math.exp(log_pmf)
    x = count
    if count >= trials * probability:
        while x < trials and term > total * TAIL_TERM_CUTOFF:
            term *= (trials - x) / (x + 1) * probability / (1 - probability)
            x += 1
            total += term
    else:
        while x > 0 and term > total * TAIL_TERM_CUTOFF:
            term *= x / (trials - x + 1) * (1 - probability) / probability
            x -= 1
            total += term

    return min(1.0, 2 * total)


def uniform(cells: int) -> tuple[float, ...]:
    """
    Equal probabilities over `cells` outcomes.
    """
    return (1 / cells,) * cells


@dataclass(frozen=True)
class FamilySummary:
    """
    The verdict on a cell family: the tail of its most extreme cell, times the number of cells, against the alarm rate.
    """

    name: str
    cells: int
    trials: int
    min_expected: float
    max_z: float
    max_cell: tuple[int, int]
    tail_p: float
    tail_cell: tuple[int, int]
    family_p: float
    exact: bool
    status: Status


@dataclass
class CellFamily:
    """
    Counts over rows x columns, every row a run of the same number of trials with the same column probabilities.

    The reference is exact, so each cell gets a z score and, when it is extreme, an exact binomial tail; the family
    warns when the most extreme cell's tail times the number of cells, a union bound on the family's false-alarm
    probability, falls under the alarm rate. A pooled histogram would hide a biased position, which is why the wall
    checks are matrices over positions. `variance_factor` scales the binomial variance for trials drawn without
    replacement (a hypergeometric count), whose tails then use the normal approximation.
    """

    name: str
    probabilities: tuple[float, ...]
    rows: int = 1
    variance_factor: float = 1.0
    trials: int = 0
    counts: list[list[int]] = field(init=False)

    def __post_init__(self) -> None:
        self.counts = [[0] * len(self.probabilities) for _ in range(self.rows)]

    def add(self, row: int, column: int) -> None:
        """
        Count one outcome in a row; the caller advances `trials` once per trial of every row.
        """
        self.counts[row][column] += 1

    def summary(self) -> FamilySummary:
        """
        Score every cell and report the most extreme one.
        """
        scores = self._scores()
        most_deviant = max(scores, key=lambda score: abs(score[0]))
        max_z, max_cell = most_deviant[:2]
        exact = self.variance_factor == 1.0
        candidates = [score for score in scores if abs(score[0]) >= EXACT_TAIL_FROM_Z] or [most_deviant]
        tails = [(self._tail(z, count, cell[1]), cell) for z, cell, count in candidates]
        tail_p, tail_cell = min(tails, key=lambda tail: tail[0])
        cells = self.rows * len(self.probabilities)
        family_p = min(1.0, cells * tail_p)
        min_expected = self.trials * min(self.probabilities)
        if min_expected < MIN_EXPECTED_PER_CELL:
            status = Status.INSUFFICIENT
        else:
            status = Status.WARN if family_p < FAMILY_ALARM_RATE else Status.OK

        return FamilySummary(
            name=self.name,
            cells=cells,
            trials=self.trials,
            min_expected=min_expected,
            max_z=max_z,
            max_cell=max_cell,
            tail_p=tail_p,
            tail_cell=tail_cell,
            family_p=family_p,
            exact=exact,
            status=status,
        )

    def _scores(self) -> list[tuple[float, tuple[int, int], int]]:
        scores = []
        for row, row_counts in enumerate(self.counts):
            for column, count in enumerate(row_counts):
                probability = self.probabilities[column]
                deviation = math.sqrt(self.trials * probability * (1 - probability) * self.variance_factor)
                z = (count - self.trials * probability) / deviation if deviation > 0 else 0.0
                scores.append((z, (row, column), count))

        return scores

    def _tail(self, z: float, count: int, column: int) -> float:
        if self.variance_factor != 1.0:
            return two_sided_tail(z)

        return binomial_two_sided_tail(self.trials, self.probabilities[column], count)

    def to_json(self) -> dict[str, Any]:
        """
        The summary with the raw counts and probabilities, so a reader can recompute any cell.
        """
        summary = self.summary()
        return {
            **summary.__dict__,
            "status": summary.status.value,
            "probabilities": list(self.probabilities),
            "variance_factor": self.variance_factor,
            "counts": self.counts,
        }


@dataclass(frozen=True)
class MeanSummary:
    """
    A mean over game clusters with its standard error, comparable to an exact value or to another summary.
    """

    name: str
    clusters: int
    events: int | None
    mean: float | None
    se: float | None
    expected: float | None
    z: float | None
    status: Status

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MeanSummary:
        return cls(
            name=data["name"],
            clusters=data["clusters"],
            events=data["events"],
            mean=data["mean"],
            se=data["se"],
            expected=data["expected"],
            z=data["z"],
            status=Status(data["status"]),
        )

    def to_json(self) -> dict[str, Any]:
        return {**self.__dict__, "status": self.status.value}


@dataclass
class MeanStat:
    """
    A running mean whose observations are per-game values, since hands and rounds within one game are dependent.

    With an `expected` value the summary tests the mean against it; without one it is only a side of a comparison.
    `events` is the pooled count behind a fraction, so a rare bin is judged by how often it happened, not by how many
    games were played.
    """

    name: str
    expected: float | None = None
    events: int | None = None
    clusters: int = 0
    total: float = 0.0
    total_sq: float = 0.0

    def add(self, value: float) -> None:
        """
        Record one game's value.
        """
        self.clusters += 1
        self.total += value
        self.total_sq += value * value

    @property
    def mean(self) -> float | None:
        return self.total / self.clusters if self.clusters else None

    @property
    def se(self) -> float | None:
        if self.clusters < 2:
            return None

        variance = max(self.total_sq - self.total * self.total / self.clusters, 0.0) / (self.clusters - 1)
        return math.sqrt(variance / self.clusters)

    def summary(self) -> MeanSummary:
        """
        The mean, its standard error and, given an expected value, the z score against it.

        A constant sample has no standard error: it is ok when it equals the expectation and degenerate otherwise,
        never a z score and never hidden as insufficient.
        """
        mean, se = self.mean, self.se
        z = None
        if self.expected is None:
            status = Status.OK
        elif mean is None or se is None or not self._sufficient:
            status = Status.INSUFFICIENT
        elif se == 0:
            status = Status.OK if mean == self.expected else Status.DEGENERATE
        else:
            z = (mean - self.expected) / se
            status = Status.WARN if abs(z) > warn_threshold(1) else Status.OK

        return MeanSummary(
            name=self.name,
            clusters=self.clusters,
            events=self.events,
            mean=mean,
            se=se,
            expected=self.expected,
            z=z,
            status=status,
        )

    @property
    def _sufficient(self) -> bool:
        return self.clusters >= MIN_CLUSTERS and (self.events is None or self.events >= MIN_EVENTS)


@dataclass(frozen=True)
class Comparison:
    """
    Two mean summaries of the same quantity from different sources and the z score of their difference.
    """

    name: str
    left: MeanSummary
    right: MeanSummary
    z: float | None
    status: Status


def compare(left: MeanSummary, right: MeanSummary, threshold: float) -> Comparison:
    """
    Score the difference of two independent means by their combined standard error.

    Two constant samples are ok when equal and degenerate otherwise; one constant side still yields a z score from the
    other side's variance. A pair of rare bins needs enough events between them before it is judged at all.
    """
    z = None
    events_known = left.events is not None and right.events is not None
    enough_events = not events_known or (left.events or 0) + (right.events or 0) >= 2 * MIN_EVENTS
    unknown = left.mean is None or right.mean is None or left.se is None or right.se is None
    if unknown or min(left.clusters, right.clusters) < MIN_CLUSTERS or not enough_events:
        status = Status.INSUFFICIENT
    elif left.se == 0 and right.se == 0:
        status = Status.OK if left.mean == right.mean else Status.DEGENERATE
    else:
        z = (left.mean - right.mean) / math.sqrt(left.se**2 + right.se**2)
        status = Status.WARN if abs(z) > threshold else Status.OK

    return Comparison(name=left.name, left=left, right=right, z=z, status=status)


@dataclass
class FractionHistogram:
    """
    Per-bin fractions of a game's observations, each bin a MeanStat over games, plus the raw pooled counts.
    """

    name: str
    labels: tuple[str, ...]
    bins: list[MeanStat] = field(init=False)
    total: MeanStat = field(init=False)

    def __post_init__(self) -> None:
        self.bins = [MeanStat(f"{self.name} = {label}", events=0) for label in self.labels]
        self.total = MeanStat(f"{self.name}, mean")

    def add_game(self, values: list[int], offset: int) -> None:
        """
        Record one game's observations; `offset` maps the smallest value onto bin 0.
        """
        game_counts = [0] * len(self.labels)
        for value in values:
            game_counts[value + offset] += 1

        for stat, count in zip(self.bins, game_counts, strict=True):
            stat.add(count / len(values))
            stat.events = (stat.events or 0) + count

        self.total.add(sum(values) / len(values))

    def summaries(self) -> list[MeanSummary]:
        """
        One summary per bin followed by the mean.
        """
        return [*(stat.summary() for stat in self.bins), self.total.summary()]
