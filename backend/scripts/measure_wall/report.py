from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from scripts.measure_wall.metrics import (
    FAMILY_ALARM_RATE,
    WARNING_STATUSES,
    Comparison,
    MeanSummary,
    compare,
    warn_threshold,
)

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.measure_wall.measurement import Report

SCHEMA_VERSION = 1


def format_number(value: float | None, digits: int = 3) -> str:
    """
    Render a number with fixed decimals, or a dash when it is unknown.
    """
    return "-" if value is None else f"{value:.{digits}f}"


def format_probability(value: float) -> str:
    """
    Render a tail probability: fixed decimals when it is ordinary, scientific when it is small.
    """
    return f"{value:.3f}" if value >= 0.001 else f"{value:.1e}"


def render_text(report: Report) -> str:
    """
    Render the report as the tables the terminal shows.
    """
    sections = [
        _render_header(report),
        _render_families(report),
        _render_means(report),
        _render_comparisons(report),
        _render_cross_round(report),
        _render_verdict(report),
    ]
    return "\n\n".join(section for section in sections if section)


def _render_header(report: Report) -> str:
    meta = report.metadata
    size = f"{meta['games']} games x {meta['rounds']} rounds = {report.walls} walls"
    lines = [
        "WALL GENERATOR MEASUREMENT",
        f"  rng {meta['rng_version']}, seed {meta['seed_bytes']} bytes, {size}, experiment {meta['experiment_seed']}",
        f"  elapsed {meta['elapsed_seconds']:.1f}s, {meta['walls_per_second']:.0f} walls/s, python {meta['python']}",
    ]
    if report.errors:
        lines.append(f"  structure: {len(report.errors)} ERRORS")
        lines.extend(f"    {error}" for error in report.errors)
    else:
        lines.append(f"  structure: ok ({report.walls} walls own every tile once, the first game regenerates equal)")

    return "\n".join(lines)


def _render_families(report: Report) -> str:
    columns = f"{'cells':>6} {'trials':>7} {'min exp':>8} {'max z':>6} {'tail p':>8} {'at':>8} {'x cells':>8}  status"
    lines = [
        f"CELL FAMILIES (exact reference; warn when the extreme cell's tail x cells is under {FAMILY_ALARM_RATE:.1%})",
        f"  {'name':56} {columns}",
    ]
    for family in report.families:
        cell = f"{family.tail_cell[0]},{family.tail_cell[1]}"
        tail = format_probability(family.tail_p) + ("" if family.exact else "~")
        lines.append(
            f"  {family.name:56} {family.cells:>6} {family.trials:>7} {family.min_expected:>8.1f} "
            f"{family.max_z:>6.2f} {tail:>8} {cell:>8} {format_probability(family.family_p):>8}  {family.status.value}",
        )

    lines.append("  tail p: exact binomial, or ~ normal with hypergeometric variance; x cells: a union bound")
    return "\n".join(lines)


def _render_means(report: Report) -> str:
    lines = [
        "MEANS PER GAME (exact reference; the standard error treats each game as one observation)",
        f"  {'name':56} {'observed':>9} {'expected':>9} {'se':>7} {'z':>6}  status",
    ]
    lines.extend(_mean_row(summary) for summary in report.means)
    return "\n".join(lines)


def _mean_row(summary: MeanSummary) -> str:
    return (
        f"  {summary.name:56} {format_number(summary.mean):>9} {format_number(summary.expected):>9} "
        f"{format_number(summary.se, 4):>7} {format_number(summary.z, 1):>6}  {summary.status.value}"
    )


def _render_comparisons(report: Report) -> str:
    lines = [
        f"STARTING HANDS vs control ({report.control_method})",
        f"  {'name':56} {'engine':>9} {'control':>9} {'z':>6}  status   {'engine n':>9} {'control n':>9}",
    ]
    lines.extend(_comparison_row(comparison) for comparison in report.comparisons)
    return "\n".join(lines)


def _comparison_row(comparison: Comparison) -> str:
    counts = ""
    if comparison.left.events is not None and comparison.right.events is not None:
        counts = f"{comparison.left.events:>9} {comparison.right.events:>9}"

    return (
        f"  {comparison.name:56} {format_number(comparison.left.mean, 4):>9} "
        f"{format_number(comparison.right.mean, 4):>9} {format_number(comparison.z, 1):>6}  "
        f"{comparison.status.value:12} {counts}"
    )


def _render_cross_round(report: Report) -> str:
    if report.consecutive_pairs == 0:
        return ""

    verdict = "ok" if report.identical_walls == 0 else "WARN"
    return (
        "CONSECUTIVE ROUNDS OF ONE SEED\n"
        f"  identical walls: {report.identical_walls} of {report.consecutive_pairs} pairs  {verdict}"
    )


def _render_verdict(report: Report) -> str:
    warnings = [family.name for family in report.families if family.status in WARNING_STATUSES]
    warnings.extend(summary.name for summary in report.means if summary.status in WARNING_STATUSES)
    warnings.extend(comparison.name for comparison in report.comparisons if comparison.status in WARNING_STATUSES)
    if report.identical_walls:
        warnings.append("identical consecutive walls")

    if not warnings:
        return (
            "No statistical warnings. Under a correct generator each family warns with at most a "
            f"{FAMILY_ALARM_RATE:.1%} chance (a union bound over its cells), so a warning is a prompt to rerun, "
            "not a proof."
        )

    return "STATISTICAL WARNINGS (rerun with another experiment seed before reading anything into one):\n" + "\n".join(
        f"  {name}" for name in warnings
    )


def to_json(report: Report, families: list[dict[str, Any]]) -> dict[str, Any]:
    """
    The whole report with raw family counts, as a baseline for a later run.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": report.metadata,
        "errors": report.errors,
        "games": report.games,
        "walls": report.walls,
        "consecutive_pairs": report.consecutive_pairs,
        "identical_walls": report.identical_walls,
        "families": families,
        "means": [summary.to_json() for summary in report.means],
        "comparisons": [
            {"name": comparison.name, "z": comparison.z, "status": comparison.status.value}
            for comparison in report.comparisons
        ],
        "engine_hands": [comparison.left.to_json() for comparison in report.comparisons],
        "control_hands": [comparison.right.to_json() for comparison in report.comparisons],
    }


def comparable_means(report: Report) -> dict[str, MeanSummary]:
    """
    Every per-game mean of the run by name: the exact-reference means and the engine's hand statistics.
    """
    summaries = [*report.means, *(comparison.left for comparison in report.comparisons)]
    return {summary.name: summary for summary in summaries}


def render_baseline(report: Report, baseline_path: Path) -> str:
    """
    Compare this run's per-game means with those a saved JSON report holds.

    Two runs with the same experiment seed and seed size play the same engine seeds, so their statistics are paired
    and their covariance is not saved: they get descriptive differences only. Independent runs get a z score.
    """
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        return f"BASELINE {baseline_path}: schema {data.get('schema_version')} is not {SCHEMA_VERSION}, not compared"

    baseline = {summary["name"]: MeanSummary.from_json(summary) for summary in (*data["means"], *data["engine_hands"])}
    current = comparable_means(report)
    shared = [name for name in current if name in baseline]
    meta = data["metadata"]
    paired = all(meta[key] == report.metadata[key] for key in ("experiment_seed", "seed_bytes"))
    size = f"{meta['games']} games x {meta['rounds']} rounds, {meta['rng_version']}, seed {meta['seed_bytes']} bytes"
    lines = [f"BASELINE {baseline_path} ({size})"]
    if data["errors"]:
        lines.append(f"  the baseline run had {len(data['errors'])} structural errors")

    if paired:
        lines.append(
            "  same experiment seed: the runs share their engine seeds, so only the differences are shown; "
            "rerun with another --experiment-seed for an independent comparison with a z score",
        )
        lines.append(f"  {'name':56} {'baseline':>9} {'current':>9} {'diff':>8}")
        lines.extend(_paired_row(name, baseline[name], current[name]) for name in shared)
        return "\n".join(lines)

    threshold = warn_threshold(max(len(shared), 1))
    lines.append(f"  {'name':56} {'baseline':>9} {'current':>9} {'z':>6}  status")
    lines.extend(_independent_row(compare(current[name], baseline[name], threshold)) for name in shared)
    return "\n".join(lines)


def _paired_row(name: str, baseline: MeanSummary, current: MeanSummary) -> str:
    difference = None if baseline.mean is None or current.mean is None else current.mean - baseline.mean
    return (
        f"  {name:56} {format_number(baseline.mean, 4):>9} {format_number(current.mean, 4):>9} "
        f"{format_number(difference, 4):>8}"
    )


def _independent_row(comparison: Comparison) -> str:
    return (
        f"  {comparison.name:56} {format_number(comparison.right.mean, 4):>9} "
        f"{format_number(comparison.left.mean, 4):>9} {format_number(comparison.z, 1):>6}  {comparison.status.value}"
    )
