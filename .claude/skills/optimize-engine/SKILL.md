---
name: optimize-engine
description: Profile the game engine, identify a single performance bottleneck, optimize it, and verify the improvement with before/after measurements.
model: opus
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(make profile), Bash(make profile-games), Bash(uv run --project backend python bin/profile_replay.py *), Bash(PYTHONPATH=* uv run --project backend python bin/profile_replay.py *), Bash(git worktree *), Bash(cd backend && uv run pytest *), Bash(make run-all-checks), Bash(git log *), Bash(git show *)
---

Profile the game engine replay runner, pick a single optimization, implement it, and show that the gain is larger than the measurement noise.

## Two profilers, two jobs

| | `make profile` (replay) | `make profile-games` (bot games) |
|---|---|---|
| Covers | The engine only: in one 12-table run, 37% of the game server's GIL-holding samples | The whole game server path in real games |
| Repeatable | Yes: one fixed game, interleaved A/A runs within about 1.5% | No: every bot game differs |
| Cost | About 25 s | Several minutes, and the `mahjong-bot` repo |
| Job | Proving an engine change: before/after numbers | Choosing a target: which layer and function the real server spends CPU in |

Bot games cannot prove a gain of a few percent: the games differ and each yields only about 40 samples. The replay cannot see the transport, router, session and messaging layers that hold the rest of the samples; in that 12-table run the uvicorn/websockets transport (41%) was level with the engine. One run is not a stable ranking: re-run before relying on the order of close layers. So use bot games to choose where to look, and the replay to measure engine changes. A target outside `game/logic/` is out of this skill's scope: report it, because the replay cannot measure a change there.

## How the measurement works

`make profile` (`bin/profile_replay.py`) replays the `full_game.txt` fixture (about 1,080 steps, about 0.1 s per run) three ways:

- **Timing:** 20 runs with no profiler attached, reported as median, stdev and every run. This is the only source of speed numbers. The `Engine:` line shows which checkout the engine was imported from.
- **cProfile:** one traced run, saved to `backend/profiles/replay_<timestamp>.prof`. It gives exact `ncalls` and callers. Tracing every call slows the replay about 2.2× and inflates call-heavy Python functions relative to everything else. C calls get rows of their own (pydantic-core's `validate_python` is about 5% of the run), but the engine-only tables hide them. Use it for call counts and the call graph, not to rank hotspots.
- **Sampled profile:** py-spy samples 200 runs at 100 Hz in a child process (about 2,300 samples) and saves `replay_<timestamp>.samples.txt`. Its blocking mode pauses the child for every sample, so it perturbs the run; it distorts call-heavy code far less than tracing, so rank hotspots by its tables, and claim gains only from the unprofiled timing. Without native stacks, time inside C code (pydantic-core, `Counter.update`) is charged to the Python function that called it. Shares cover the samples inside `run_replay_loop`: one replay load, then the loops with their between-call cleanup. Imports are left out. The script fails when py-spy loses samples or falls behind; at higher rates it falls behind on this VM and stalls the child, which skews the shares. Repeated profiles agree within about 1.5 points, so treat closer shares as a tie.

The timed work is the engine plus the replay harness, which builds a `ReplayStep` per step and keeps the whole trace; `handle_action` is about 92% of the samples.

Noise on this host: the 20 runs inside one invocation have a 4–6% stdev, and the median drifts by up to 6% between invocations. A single `make profile` before and one after cannot show a gain below that, so Step 7 compares alternating runs against a baseline checkout. Interleaved A/A runs land within about 1.5% of each other.

Fix hotspots in the engine's own code. When only a runtime knob would help (GC thresholds, interpreter flags, a Python upgrade), report it as an option with its trade-off and do not implement it.

## Step 0: Check where real games spend server CPU (optional)

Run this when the target is not chosen yet, or when the last bot-game profile is older than the engine changes since:

```
make profile-games
```

It plays 48 bot games, 12 tables at a time (about 2 minutes), with the game server under py-spy and logging at production's INFO level. py-spy runs with `--gil`: it samples only the thread holding the GIL, so idle waits drop out, but the shares are of GIL-holding stack samples, not CPU time. A native call or syscall made with the GIL held counts toward its Python caller (uvloop writes to sockets this way), and work that releases the GIL, such as SQLite, does not count. `--native` and line-level sampling both fail under load on this VM. The run also prints the game server's CPU-seconds per game, read from `/proc`, which is CPU time. It prints the samples by layer, the top functions by self time, and the top project functions by inclusive time, and fails when py-spy loses samples or falls behind. It kills whatever holds `:8710`/`:8711` and wipes `backend/logs`; replays already in the replay dir are kept.

- The layer table charges each sample to its deepest project or server-library frame, so library code counts toward the layer that called it.
- Report every layer outside the engine with a large share, with its top functions, as a finding: the replay cannot measure a change there.
- Continue with Step 1 when an engine function is high in both this profile and the replay's; it is the best engine target. When none is, stop after the report.

## Step 1: Baseline

Start from a clean working tree. Check out the current commit as the baseline for Step 7, with `S` set to your scratchpad directory:

```
git worktree add --detach $S/perf-baseline HEAD
```

Then profile:

```
make profile
```

Record the median, the stdev, and the top rows of both sampled tables.

## Step 2: Load cProfile details

```
uv run --project backend python bin/profile_replay.py --load
```

This shows the cProfile run by cumulative time, by self time, and the callers of the top 10 functions. Read it for `ncalls` and for who calls a hotspot, not for time shares.

## Step 3: Review past performance work

Find previous performance commits:

```
git log --all --grep='!perf' --format='%H %s'
```

Read the `--stat` summaries first, then the full diffs only of commits that touched the current hotspots:

```
git show <commit-hash> --stat
git show <commit-hash>
```

Use them to avoid redoing past work, to reuse patterns that worked, and to find areas nobody has touched yet.

## Step 4: Identify a single improvement

Pick **one** function to optimize:

- Start from the sampled **self time** table: that is where the CPU actually goes, library frames included. A large library share (pydantic `model_copy`, `copy.copy`, structlog) points to the engine function that calls it too often; find that caller in the inclusive table and in the Step 2 callers.
- The sampled **inclusive** table shows which engine path owns the time. The hotspot is the deepest frame that still has a large share.
- Use cProfile `ncalls` to spot redundant calls: a function called far more often than the replay has steps.
- Skip functions that past `!perf` commits already optimized, unless the profile shows they are still on top.

Read the source code of the target function and its callers.

### Optimization strategies to consider

- Skip work that cannot change the result: early returns, recomputing only what changed
- Reduce model copies and validation on the hot path
- Cache frequently called pure functions with `@lru_cache`
- Better algorithms or data structures (less backtracking, pruning, cheaper lookups)
- Inline a hot-path call only when the sampled profile, not cProfile, shows the call overhead
- Keep `is_pair`, `is_honor` and similar helpers in place for readability

### When no optimization is possible

If the top functions are already efficient and no single change would yield a measurable improvement without significant architectural changes, report this clearly:

- List the top 3-5 functions by sampled self time and why each is already optimal
- Note any potential improvements that would require larger refactors
- Remove the baseline worktree and stop — do not force unnecessary changes

## Step 5: Implement the optimization

Make the change. Keep it focused — one optimization per run. Do not refactor surrounding code. Do not touch `game/replay/`: Step 7 imports it from the baseline too, so a harness change would mix into the engine numbers.

## Step 6: Check correctness

Run the replay tests, which pin the engine's output for whole games, plus the tests of the module you changed:

```
cd backend && uv run pytest game/tests/integration/replays <tests of the changed module>
```

## Step 7: Verify the improvement

Run baseline (A) and candidate (B) in the balanced order A B B A A B, one invocation each. `--sample-loops 0` skips the sampled profile, and `PYTHONPATH` makes the script import the engine from the baseline worktree:

```
PYTHONPATH=$S/perf-baseline/backend uv run --project backend python bin/profile_replay.py --sample-loops 0
uv run --project backend python bin/profile_replay.py --sample-loops 0
```

Check each run's `Engine:` line names the checkout you meant, and record its `Median time`. Compare the median of each side's three medians, and classify the result:

- **Improvement:** all three B medians are below all three A medians.
- **Regression:** all three B medians are above all three A medians.
- **Inconclusive:** the ranges overlap. Run three more of each in the same order before calling it; if they still overlap, the effect is below what this setup resolves. Revert it and report it as unresolved, not as zero.

Non-overlap is a heuristic, not a statistical test, so report the spread with the gain.

Run `make profile` once more and check the change you predicted in Step 4: a lower `ncalls` (from `--load`) for a removed redundant call, a lower sampled share for cheaper work. A share can rise while absolute cost falls if other work fell more.

Remove the baseline worktree:

```
git worktree remove $S/perf-baseline
```

## Step 8: Run all checks

```
make run-all-checks
```

It always exits 0: success is only the final `All checks are good` line. If a check fails, fix it or revert the optimization.

## Step 9: Report results

Summarize in a table:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Median time, 3 alternating invocations each (range) | X ms (a–b) | Y ms (c–d) | -Z% |
| Target function sampled self share | X% | Y% | |
| Target function ncalls | X | Y | -Z% |

Then:

- **Does it matter:** the per-step cost before and after (median / trace steps).
- **Not measured:** one all-human fixture game, so no AI player decisions; none of the session, messaging or server layers (shaping and MessagePack-encoding a game's events for every recipient takes about 5% of the engine's time, without replay collection, routing or input validation); logging set to CRITICAL, so log calls cost less here than in production; no event loop or concurrent tables. A gain here does not show how the server will respond under load.
