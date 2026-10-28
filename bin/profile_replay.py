from __future__ import annotations

import argparse
import cProfile
import logging
import pstats
import statistics
import sys
import time
from pathlib import Path

import game
from game.replay import load_replay_from_file, run_replay
from game.replay.models import ReplayInput, ReplayTrace
from sampled_profile import CpuSampler, ProfileKey, format_func, print_sampled_profile
from shared.logging import setup_logging

DEFAULT_REPLAY = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "game"
    / "tests"
    / "integration"
    / "replays"
    / "fixtures"
    / "full_round"
    / "full_game.txt"
)
PROFILE_DIR = Path(__file__).resolve().parent.parent / "backend" / "profiles"
ITERATIONS = 20
SAMPLE_LOOPS = 200
TABLE_LIMIT = 30


def profile_replay(*, sampled: bool) -> None:
    """Profile the replay fixture with timed iterations, cProfile and, when asked, a sampled profile."""
    replay = load_replay_from_file(DEFAULT_REPLAY)
    print(f"Loaded replay: {DEFAULT_REPLAY.name}")
    print(f"  Seed: {replay.seed[:16]}...")
    print(f"  Players: {', '.join(replay.player_names)}")
    print(f"  Events: {len(replay.events)}")
    print()

    # Suppress logging during profiling to keep output clean
    setup_logging(level=logging.CRITICAL)

    # Warmup + profile (separate from timing to avoid cProfile overhead)
    profiler = cProfile.Profile()
    profiler.enable()
    trace = run_replay(replay)
    profiler.disable()

    # Timed iterations (no profiler overhead)
    elapsed_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        run_replay(replay)
        elapsed_times.append(time.perf_counter() - start)

    # Save profile
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    profile_file = PROFILE_DIR / f"replay_{timestamp}.prof"
    profiler.dump_stats(str(profile_file))

    # Print results
    _print_performance_stats(replay, trace, elapsed_times, profile_file)
    _print_top_functions(profiler)

    if sampled:
        sample_file = PROFILE_DIR / f"replay_{timestamp}.samples.txt"
        _record_samples(replay, sample_file)
        print_sampled_profile(sample_file, root=run_replay_loop.__name__, by_layer=False)


def run_replay_loop(replay: ReplayInput) -> None:
    """Run the replay SAMPLE_LOOPS times, the work the sampled profile covers."""
    for _ in range(SAMPLE_LOOPS):
        run_replay(replay)


def _record_samples(replay: ReplayInput, output: Path) -> None:
    sampler = CpuSampler()
    sampler.start()
    try:
        run_replay_loop(replay)
    finally:
        sampler.stop()

    sampler.write(output)


def _print_performance_stats(
    replay: ReplayInput,
    trace: ReplayTrace,
    elapsed_times: list[float],
    profile_file: Path,
) -> None:
    """Print benchmark performance statistics."""
    median_time = statistics.median(elapsed_times)
    num_steps = len(trace.steps)

    print("=" * 60)
    print("PERFORMANCE")
    print("=" * 60)
    print(f"Engine: {Path(game.__file__).parent}")
    print(f"Replay events: {len(replay.events)}")
    print(f"Trace steps: {num_steps}")
    print(f"Iterations: {len(elapsed_times)}")
    print(f"Median time: {median_time * 1000:.1f}ms")
    print(f"Min time: {min(elapsed_times) * 1000:.1f}ms")
    print(f"Max time: {max(elapsed_times) * 1000:.1f}ms")
    print(f"Throughput: {num_steps / median_time:.0f} steps/sec (based on median)")

    if len(elapsed_times) > 1:
        stdev = statistics.stdev(elapsed_times)
        print(f"Stdev: {stdev * 1000:.1f}ms ({100 * stdev / median_time:.1f}% of median)")
        print(f"All runs: {', '.join(f'{t * 1000:.1f}' for t in elapsed_times)} ms")

    print(f"Profile saved to: {profile_file}")
    print()


def _is_engine_code(filename: str) -> bool:
    """Return True if filename belongs to the game engine (not replay/tests/libs)."""
    if "game/" not in filename:
        return False
    return "game/replay/" not in filename and "game/tests/" not in filename


def _collect_engine_entries(
    stats: pstats.Stats,
    sort_key: str,
    limit: int,
) -> list[tuple[ProfileKey, int, int, float, float]]:
    """Collect engine-only profile entries sorted by the given key."""
    stats.sort_stats(sort_key)
    entries = []
    for key in stats.stats:
        if not _is_engine_code(key[0]):
            continue
        cc, nc, tt, ct, _ = stats.stats[key]
        entries.append((key, cc, nc, tt, ct))

    sort_index = 3 if sort_key == "tottime" else 4  # tt or ct
    entries.sort(key=lambda e: e[sort_index], reverse=True)
    return entries[:limit]


def _print_entries_table(
    entries: list[tuple[ProfileKey, int, int, float, float]],
) -> None:
    """Print a formatted table of profile entries."""
    print(f"{'ncalls':>9}  {'tottime':>8}  {'percall':>8}  {'cumtime':>8}  {'percall':>8}  filename:lineno(function)")
    for key, cc, nc, tt, ct in entries:
        calls = str(nc) if cc == nc else f"{nc}/{cc}"
        tt_pc = tt / nc if nc else 0
        ct_pc = ct / cc if cc else 0
        print(f"{calls:>9}  {tt:>8.3f}  {tt_pc:>8.3f}  {ct:>8.3f}  {ct_pc:>8.3f}  {format_func(key)}")


def _print_top_functions(profiler: cProfile.Profile) -> None:
    """Print top functions by cumulative time, showing only game engine code."""
    stats = pstats.Stats(profiler)
    entries = _collect_engine_entries(stats, "cumulative", TABLE_LIMIT)
    print(f"Top {TABLE_LIMIT} game engine functions by cumulative time:")
    _print_entries_table(entries)
    print()


def _find_latest_profile() -> Path | None:
    """Find the most recently modified .prof file in the profiles directory."""
    if not PROFILE_DIR.exists():
        return None
    profiles = sorted(PROFILE_DIR.glob("*.prof"), key=lambda p: p.stat().st_mtime)
    return profiles[-1] if profiles else None


def load_profile() -> None:
    """Load the latest .prof file and display detailed engine-only analysis."""
    profile_path = _find_latest_profile()
    if profile_path is None:
        print(f"No profile found in {PROFILE_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading profile: {profile_path.name}")
    stats = pstats.Stats(str(profile_path))
    print()

    # Top functions by cumulative time
    cum_entries = _collect_engine_entries(stats, "cumulative", TABLE_LIMIT)
    print(f"Top {TABLE_LIMIT} game engine functions by cumulative time:")
    _print_entries_table(cum_entries)
    print()

    # Top functions by total (self) time
    tot_entries = _collect_engine_entries(stats, "tottime", TABLE_LIMIT)
    print(f"Top {TABLE_LIMIT} game engine functions by total (self) time:")
    _print_entries_table(tot_entries)
    print()

    # Callers for the top 10 cumulative-time functions
    top_keys = {entry[0] for entry in cum_entries[:10]}
    print("=" * 60)
    print("CALLERS for top 10 functions")
    print("=" * 60)
    for key, _, nc, _, ct in cum_entries[:10]:
        print(f"\n{format_func(key)}  (cumtime={ct:.3f}s, ncalls={nc})")
        callers = stats.stats[key][4]
        if not callers:
            print("  (no callers recorded)")
            continue
        # Sort callers by cumulative time contributed
        caller_list = []
        for caller_key, caller_data in callers.items():
            # caller_data: (nc, cc, tt, ct)
            c_nc, _, c_tt, c_ct = caller_data
            caller_list.append((caller_key, c_nc, c_tt, c_ct))
        caller_list.sort(key=lambda c: c[3], reverse=True)
        for caller_key, c_nc, c_tt, c_ct in caller_list[:5]:
            tag = " *" if caller_key in top_keys else ""
            print(f"  <- {format_func(caller_key)}  ncalls={c_nc}  tottime={c_tt:.3f}s  cumtime={c_ct:.3f}s{tag}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile the full_game.txt replay")
    parser.add_argument("--load", action="store_true", help="show the latest cProfile run in detail instead")
    parser.add_argument("--timing-only", action="store_true", help="skip the sampled profile")
    args = parser.parse_args()

    if args.load:
        load_profile()
        return

    profile_replay(sampled=not args.timing_only)


if __name__ == "__main__":
    main()
