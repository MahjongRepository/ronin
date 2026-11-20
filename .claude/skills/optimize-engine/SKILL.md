---
name: optimize-engine
description: Profile the Go game server, identify a single performance bottleneck, optimize it, and verify the improvement with before/after measurements.
model: opus
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(make profile), Bash(make profile *), Bash(make profile-compare *), Bash(make profile-games), Bash(make update-pgo), Bash(make lint-go), Bash(git worktree *), Bash(cd backend/game_v2 && mise exec -- go test *), Bash(cd backend/game_v2 && mise exec -- go tool pprof *), Bash(make run-all-checks), Bash(git log *), Bash(git show *)
---

Profile the Go game server (`backend/game_v2`), pick a single optimization, implement it, and show that `benchstat` resolves the gain from noise.

## Three measurements, three jobs

| | `make profile` (full-game benchmarks) | `make profile-compare` (A/B) | `make profile-games` (bot games) |
|---|---|---|---|
| Covers | One fixed game: `engine` through the engine alone, `router` through Router, session, store and wire in process, `socket` from `POST /games` to the closing frames over real websockets | The same benchmarks, a baseline checkout against the working tree | The whole server in real games, sockets and timers included |
| Repeatable | Yes | Yes: alternating rounds, `benchstat` p-values | No: every bot game differs |
| Cost | About 45 s | About 2 min | About 1 minute, and the `mahjong-bot` repo (`BOT_ROOT`, default `~/work/mahjong-bot`) |
| Job | Choosing an engine or session target, call graphs, allocations | Proving a change | Choosing a layer: where the real server spends CPU |

All three benchmarks play the client's `full_game.msgpack` fixture (1,046 engine steps, 7,022 messages out on the server side). The fixture is played by the default policy: discards and passes, no calls, so the call paths are thin in all of them. `socket` runs four websocket clients on loopback in the same process: they only count frames, but their read syscalls are about a quarter of its CPU (the `internal/server_test` layer), and its wall time is mostly round trips, so judge a socket change by its `cpu-ns/op` (`cpu-sec/op` in `benchstat`), the process's CPU per game. Only one table plays at a time: contention between games shows only in `make profile-games`.

## How the measurement works

`make profile [BENCH=engine|router|socket]` (`bin/profile-full-game.sh`) runs each benchmark 10 times with `-benchmem`, a CPU profile and an allocation profile, into `backend/profiles/<name>_<timestamp>/`, and prints:

- **`benchstat`:** the median `sec/op` with its 95% confidence interval, plus `B/op`, `allocs/op`, the custom `steps/op` and `messages/op`, and `socket`'s `cpu-ns/op`. Allocation counts are exact and repeat run to run, so a change in `allocs/op` is real even when time is in the noise.
- **CPU by layer:** each sample charged to the deepest package of this module on its stack, so library and runtime work counts toward the package that called it, except GC work, which gets its own `runtime GC` row. A large GC row points at allocations, not at the GC.
- **Top functions by self CPU,** and **project functions by inclusive CPU** (`-show` of the module).
- **Allocations:** top functions by bytes allocated, and project functions by objects allocated, inclusive. In Go most CPU wins on this code come from allocating less: every escape to the heap costs `mallocgc` now and GC work later.

Go's CPU profiler samples every goroutine at 100 Hz with little distortion, so its shares rank hotspots directly. Read the details with `cd backend/game_v2 && mise exec -- go tool pprof`:

- `-peek '<regex>'` for a function's callers and callees (Go profiles have no call counts: count calls by reasoning from `-peek` and the code, or with a throwaway counter in a scratch test).
- `-list '<regex>'` for line-level cost, `-sample_index=alloc_space -list` on `allocs.prof` for line-level allocations.
- `-http=:` for the graph and flame view.
- `go test -gcflags=-m=1 ./<pkg> 2>&1 | grep '<file>'` shows which values escape to the heap and why.

All three targets build with `cmd/gameserver/default.pgo`, the PGO profile production builds use, so they measure the shipped code. The benchmarks spread 3–7% within one run. Interleaved A/A runs of the same code land within noise (p > 0.5), so the A/B below resolves changes of a few percent.

Fix hotspots in the server's own code. When only a runtime knob would help (`GOGC`, `GOMEMLIMIT`, `GOMAXPROCS`, a Go upgrade, a PGO refresh), report it as an option with its trade-off and do not implement it.

## Step 0: Check where real games spend server CPU (optional)

Run this when the target is not chosen yet, or when the last bot-game profile is older than the server changes since:

```
make profile-games
```

It plays 48 bot games, 12 tables at a time, at production's INFO logging, with `cmd/gameserver -profiledir` writing `cpu.prof`, `allocs.prof`, `mutex.prof` and `runtime.json` into `backend/profiles/games_<timestamp>/` as the server stops. It prints the per-game CPU from `/proc`, then the same report as `make profile` plus mutex contention and the runtime's totals (busy CPU, GC CPU, bytes and objects allocated, mutex wait, each per game). It kills whatever holds `:8710` and `:8712`, wipes `backend/logs`, and adds its games to the dev database.

- Compare its layer table with `socket`'s: a layer much larger in real games than in `socket` (mutex waits, many tables at once, the bots' calls and wins) is something the benchmarks cannot prove; report it with its top functions as a finding.
- Continue with Step 1 when a function is high in both this profile and a benchmark's. When none is, stop after the report.

## Step 1: Baseline

Start from a clean working tree. Check out the current commit as the baseline, with `S` set to your scratchpad directory:

```
git worktree add --detach $S/perf-baseline HEAD
```

Then profile:

```
make profile
```

Record each benchmark's `sec/op`, `B/op` and `allocs/op` (and `socket`'s `cpu-ns/op`), the layer table, and the top rows of the self CPU and allocation tables.

## Step 2: Review past performance work

```
git log --all --grep='!perf' --format='%H %s'
```

Read the `--stat` summaries first, then the full diffs of commits that touched the current hotspots (`git show <hash>`). The commits before the Go port optimized the Python engine: their ideas (skip work that cannot change the result, check each discard's completing seats once) may carry over, their code does not.

## Step 3: Identify a single improvement

Pick **one** function to optimize:

- Start from the layer table and the self CPU table. A large `runtime GC` row, or `mallocgc`, `memclrNoHeapPointers`, `growslice` near the top, means the target is an allocation: find its source in the allocation tables, then `-peek` its callers.
- The inclusive table shows which path owns the time. The hotspot is the deepest frame that still has a large share.
- Prefer a target that shows in `router` or `socket` and in `profile-games` over one that shows only in `engine`'s harness (`internal/replay` keeps the whole trace, which real games never do).
- Skip what past `!perf` commits already optimized, unless the profile shows it is still on top.

Read the source of the target function and its callers, and its package's `AGENTS.md` rules: engine state is a value (`backend/game_v2/AGENTS.md`, Tests), so a change never writes a slice of a state in place.

### Optimization strategies to consider

- Allocate less: keep fixed-size values (tile counts, seat arrays) on the stack instead of in slices that escape; preallocate with the known capacity; reuse a buffer within one call; avoid converting to an interface on the hot path.
- Skip work that cannot change the result: early returns, recomputing only what changed (a seat's waits when its hand did not change).
- Better algorithms or data structures: cheaper lookups, pruning, bit sets over the 34 tile kinds.
- Inline-friendly code: a small hot function called through an interface or a closure costs its call; check with `-gcflags=-m=2` before restructuring.

### When no optimization is possible

If the top functions are already efficient and no single change would yield a measurable improvement without significant architectural changes, report this clearly:

- List the top 3–5 functions by self CPU and by allocations, and why each is already reasonable.
- Note potential improvements that would need larger refactors.
- Remove the baseline worktree and stop: do not force unnecessary changes.

## Step 4: Implement the optimization

Make the change. Keep it focused: one optimization per run. Do not refactor surrounding code. Do not touch the benchmarks, their drivers or the fixture: Step 6 builds the baseline's copy of them, so a harness change mixes into the numbers.

## Step 5: Check correctness

An engine change runs the engine's tests and the seam's proof against mahjong-rs:

```
cd backend/game_v2 && mise exec -- go test -race ./engine/... ./seam/...
```

A server-side change runs its package and the server's tests, which include the full-game pin:

```
cd backend/game_v2 && mise exec -- go test -race ./internal/<pkg> ./internal/server
```

Then `make lint-go`.

## Step 6: Verify the improvement

```
make profile-compare BASE=$S/perf-baseline
```

It builds each benchmark once per side with the same PGO profile and runs them in the order base, head, head, base, base, head, 5 runs per round, then prints `benchstat base head`. Check its `base:` and `head:` lines name the checkouts you meant. Classify each benchmark's `sec/op`, and `socket`'s `cpu-ns/op` rather than its `sec/op`:

- **Improvement:** a negative delta with `p < 0.05`.
- **Regression:** a positive delta with `p < 0.05`.
- **Inconclusive:** `~`. Run it again with `BENCH_COUNT=10`; if it is still `~`, the effect is below what this setup resolves. Revert the change and report it as unresolved, not as zero, unless `allocs/op` fell, which is exact: then keep it and report the time as unresolved.

Run `make profile` once more and check the change you predicted in Step 3: a lower share or allocation count for the target, fewer bytes from it in the allocation tables. A share can rise while absolute cost falls if other work fell more.

Remove the baseline worktree:

```
git worktree remove $S/perf-baseline
```

## Step 7: Run all checks

```
make run-all-checks
```

It always exits 0: success is only the final `All checks are good` line. If a check fails, fix it or revert the optimization. Commit with a `!perf` suffix on the subject (root `AGENTS.md`, Workflow).

## Step 8: Report results

Summarize in a table, one row group per benchmark:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| `engine` sec/op (95% CI) | X ms ± a% | Y ms ± b% | -Z% (p=…) |
| `engine` allocs/op | X | Y | -Z% |
| `router` sec/op (95% CI) | X ms ± a% | Y ms ± b% | -Z% (p=…) |
| `router` allocs/op | X | Y | -Z% |
| `socket` cpu-ns/op (95% CI) | X ms ± a% | Y ms ± b% | -Z% (p=…) |
| Target function self CPU share | X% | Y% | |

Then:

- **Does it matter:** the per-step cost before and after (`sec/op` / `steps/op`), and per message out on `router` and `socket`.
- **Not measured:** one fixture game played by the default policy, so calls, AI players and wins by ron are thin; one table, so no contention between games. A gain here does not show how the server responds under load: `make profile-games` does.
- **PGO:** whether the change moved the hot path enough that `make update-pgo` is due.
