from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PLOT_WIDTH = 300
PLOT_HEIGHT = 100
PLOT_INSET = 3
_NICE_STEPS = (1, 2, 5, 10)


@dataclass(frozen=True)
class ChartPlot:
    """
    A chart drawn in a ``PLOT_WIDTH`` by ``PLOT_HEIGHT`` box with zero ``PLOT_INSET`` above the bottom, so a flat zero
    line stays visible over the axis: one SVG ``points`` list per unbroken run of buckets, and the value at the top.
    """

    lines: tuple[str, ...]
    axis_maximum: float


def axis_maximum(peak: float) -> float:
    """
    Return the smallest 1, 2 or 5 times a power of ten at or above ``peak``, or 1 when nothing rises above zero.
    """
    if peak <= 0:
        return 1.0

    magnitude = 10 ** math.floor(math.log10(peak))
    return next(step * magnitude for step in _NICE_STEPS if peak <= step * magnitude)


def plot_buckets(buckets: Sequence[float | None]) -> ChartPlot | None:
    """
    Lay the buckets out left to right, an empty bucket ending a line; None when no bucket holds a value.

    A run of one bucket repeats its point, so the round line cap draws it as a dot.
    """
    values = [value for value in buckets if value is not None]
    if not values:
        return None

    top = axis_maximum(max(values))
    runs: list[list[str]] = [[]]
    for index, value in enumerate(buckets):
        if value is None:
            runs.append([])
            continue

        x = (index + 0.5) * PLOT_WIDTH / len(buckets)
        y = PLOT_HEIGHT - PLOT_INSET - value / top * (PLOT_HEIGHT - 2 * PLOT_INSET)
        runs[-1].append(f"{x:.2f},{y:.2f}")

    lines = tuple(" ".join(run if len(run) > 1 else run * 2) for run in runs if run)
    return ChartPlot(lines=lines, axis_maximum=top)
