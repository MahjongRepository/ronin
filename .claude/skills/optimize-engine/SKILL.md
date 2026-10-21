---
name: optimize-engine
description: Profile the game engine, identify a single performance bottleneck, optimize it, and verify the improvement with before/after measurements.
model: opus
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(uv run python bin/profile_replay.py *), Bash(uv run pytest *), Bash(make run-all-checks), Bash(git log *), Bash(git show *)
---

Profile the game engine replay runner, identify a single optimization opportunity, implement it, and verify the result.

## Step 1: Run baseline profile

Run the profiler to establish a baseline:
```
uv run python bin/profile_replay.py
```

Record from the output:
- **Median time** and **throughput** (steps/sec)
- The **profile file path** printed at the end

## Step 2: Load profile details

Load the saved profile for detailed analysis:
```
uv run python bin/profile_replay.py --load
```

This shows three sections:
1. Top functions by **cumulative time** — the call tree hotspots
2. Top functions by **total (self) time** — where CPU cycles are actually spent
3. **Callers** for the top 10 functions — how the call graph flows

## Step 3: Review past performance work

Find all previous performance-related commits to understand what has already been optimized:
```
git log --all --grep='!perf' --format='%H %s'
```

For each commit found, read the diff to understand what was changed:
```
git show <commit-hash> --stat
git show <commit-hash>
```

Review selectively — read summaries first, then inspect full diffs only for commits that touched the current profile hotspots from Step 2.

Use this context to:
- Avoid re-optimizing areas that were already addressed
- Understand the optimization patterns that worked before
- Identify areas that haven't been touched yet

## Step 4: Identify a single improvement

Cross-reference the profile output with past perf commits from Step 3 — skip functions that were already optimized in previous commits.

Pick **one** function to optimize. Focus on:
- Functions high in **total (self) time** — these are the actual CPU bottlenecks
- Functions called an unexpectedly high number of times — possible redundant calls
- Functions where cumtime >> tottime — a callee dominates, look deeper

Read the source code of the target function and its callers to understand the context.

### Optimization strategies to consider

- Inline hot-path function calls to eliminate per-call overhead in tight loops
- Expand caching with `@lru_cache` for frequently called pure functions
- Early returns to skip unnecessary computation
- Algorithm improvements (reduce backtracking, add pruning)
- Data structure optimization
- Keep `is_pair`, `is_honor` and similar helpers in place for code readability
- Review algorithms for potential improvements (e.g., sorting, searching)

### When no optimization is possible

If the top functions are already efficient and no single change would yield a measurable improvement without significant architectural changes, report this clearly:
- List the top 3-5 functions by self time and why each is already optimal
- Note any potential improvements that would require larger refactors
- Stop here — do not force unnecessary changes

## Step 5: Implement the optimization

Make the change. Keep it focused — one optimization per run. Do not refactor surrounding code.

## Step 6: Run checks

Verify correctness and code quality:
```
make run-all-checks
```

All checks must pass. If checks fail, fix them or revert the optimization.

## Step 7: Verify the improvement

Run the profiler again with the same settings:
```
uv run python bin/profile_replay.py
```

Compare against the baseline from Step 1:
- **Median time**: did it decrease?
- **Throughput**: did steps/sec increase?

Load the new profile to confirm the target function improved:
```
uv run python bin/profile_replay.py --load
```

## Step 8: Report results

Summarize in a table:

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Median time | Xs | Ys | -Z% |
| Throughput | X steps/sec | Y steps/sec | +Z% |
| Target function tottime | Xs | Ys | -Z% |
| Target function ncalls | X | Y | -Z% |

If the improvement is negligible (< 2%), note it and consider reverting.
