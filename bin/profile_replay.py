from __future__ import annotations

import argparse
import cProfile
import logging
import pstats
import statistics
import subprocess
import sys
import time
from pathlib import Path

import game
from game.replay import load_replay_from_file, run_replay
from game.replay.models import ReplayInput, ReplayTrace
from sampled_profile import (
    PY_SPY,
    SAMPLE_RATE,
    ProfileKey,
    format_func,
    print_sampled_profile,
    py_spy_output_problem,
)
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
LOOP_DONE = "replay loop finished:"


def profile_replay(replay_path: Path, iterations: int, sample_loops: int) -> None:
    """Profile a replay file with timed iterations, cProfile and a py-spy sampled profile."""
    replay = load_replay_from_file(replay_path)
    print(f"Loaded replay: {replay_path.name}")
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
    for _ in range(iterations):
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

    if sample_loops > 0:
        sample_file = PROFILE_DIR / f"replay_{timestamp}.samples.txt"
        _record_samples(replay_path=replay_path, loops=sample_loops, output=sample_file)
        print_sampled_profile(sample_file, sample_rate=SAMPLE_RATE, root=run_replay_loop.__name__, by_layer=False)


def run_replay_loop(replay_path: Path, loops: int) -> None:
    """Run a replay repeatedly with nothing else in the process, for py-spy to sample."""
    replay = load_replay_from_file(replay_path)
    setup_logging(level=logging.CRITICAL)
    for _ in range(loops):
        run_replay(replay)

    print(f"{LOOP_DONE} {loops}")


def _record_samples(replay_path: Path, loops: int, output: Path) -> None:
    """Record a py-spy profile of a child process running the replay loop.

    py-spy launches the child itself because this host's ptrace_scope of 1 blocks attaching to
    a process it did not start. Blocking mode at 100 Hz: --nonblocking drops most samples of a
    CPU-bound loop as torn stacks, and blocking at 250 Hz often falls behind and stalls the child,
    which skews the shares. py-spy can exit with "No child process" after writing a complete
    profile when the child exits mid-sample; that exit is accepted only when the child printed that
    it finished every loop and py-spy reported a valid summary.
    """
    command = [
        "uvx",
        PY_SPY,
        "record",
        "--function",
        "--rate",
        str(SAMPLE_RATE),
        "--format",
        "raw",
        "--output",
        str(output),
        "--",
        sys.executable,
        str(Path(__file__).resolve()),
        "--replay",
        str(replay_path),
        "--loop",
        str(loops),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output_text = result.stdout + result.stderr
    loops_finished = f"{LOOP_DONE} {loops}" in result.stdout
    known_exit = result.returncode == 0 or (result.returncode == 1 and "No child process" in output_text)
    if not loops_finished or not known_exit or not output.exists():
        print(f"py-spy run failed ({result.returncode}):\n{output_text}", file=sys.stderr)
        sys.exit(1)

    problem = py_spy_output_problem(output_text)
    if problem is not None:
        print(f"py-spy profile is invalid, {problem}:\n{output_text}", file=sys.stderr)
        sys.exit(1)


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
    sort_key: str = "cumulative",
    limit: int = 30,
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


def _print_top_functions(profiler: cProfile.Profile, limit: int = 30) -> None:
    """Print top functions by cumulative time, showing only game engine code."""
    stats = pstats.Stats(profiler)
    entries = _collect_engine_entries(stats, "cumulative", limit)
    print(f"Top {limit} game engine functions by cumulative time:")
    _print_entries_table(entries)
    print()


def _find_latest_profile() -> Path | None:
    """Find the most recently modified .prof file in the profiles directory."""
    if not PROFILE_DIR.exists():
        return None
    profiles = sorted(PROFILE_DIR.glob("*.prof"), key=lambda p: p.stat().st_mtime)
    return profiles[-1] if profiles else None


def load_profile(profile_path: Path | None, limit: int) -> None:
    """Load a .prof file and display detailed engine-only analysis."""
    if profile_path is None:
        profile_path = _find_latest_profile()
    if profile_path is None or not profile_path.exists():
        path_msg = str(profile_path) if profile_path else PROFILE_DIR
        print(f"No profile found: {path_msg}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading profile: {profile_path.name}")
    stats = pstats.Stats(str(profile_path))
    print()

    # Top functions by cumulative time
    cum_entries = _collect_engine_entries(stats, "cumulative", limit)
    print(f"Top {limit} game engine functions by cumulative time:")
    _print_entries_table(cum_entries)
    print()

    # Top functions by total (self) time
    tot_entries = _collect_engine_entries(stats, "tottime", limit)
    print(f"Top {limit} game engine functions by total (self) time:")
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
    parser = argparse.ArgumentParser(description="Profile replay execution with cProfile")
    parser.add_argument(
        "--replay",
        type=Path,
        default=DEFAULT_REPLAY,
        help="path to replay file (default: full_game.txt fixture)",
    )
    parser.add_argument(
        "-n",
        "--iterations",
        type=int,
        default=20,
        help="number of timed iterations (default: 20)",
    )
    parser.add_argument(
        "--sample-loops",
        type=int,
        default=200,
        help="replay runs for the py-spy sampled profile, 0 to skip it (default: 200)",
    )
    parser.add_argument("--loop", type=int, help=argparse.SUPPRESS)
    parser.add_argument(
        "--load",
        nargs="?",
        const="latest",
        metavar="PROF_FILE",
        help="load a .prof file for detailed analysis (default: latest)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="number of functions to display (default: 30)",
    )
    args = parser.parse_args()

    if args.load is not None:
        profile_path = None if args.load == "latest" else Path(args.load)
        load_profile(profile_path, args.limit)
        return

    if not args.replay.exists():
        print(f"Replay file not found: {args.replay}", file=sys.stderr)
        sys.exit(1)

    if args.loop is not None:
        run_replay_loop(replay_path=args.replay, loops=args.loop)
        return

    if args.iterations < 1:
        print("Iterations must be at least 1", file=sys.stderr)
        sys.exit(1)

    if args.sample_loops < 0:
        print("Sample loops must be 0 or more", file=sys.stderr)
        sys.exit(1)

    profile_replay(replay_path=args.replay, iterations=args.iterations, sample_loops=args.sample_loops)


if __name__ == "__main__":
    main()
