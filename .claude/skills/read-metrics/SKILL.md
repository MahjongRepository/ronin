---
name: read-metrics
description: Read production metrics (host and service load, Traefik latency and errors, game-server sockets and events, storage, backup age, game counts) as JSON from the server. Use for a question about production load, latency, sockets, storage or game counts.
allowed-tools: Read
---

Both commands are read-only against production (`TARGET` defaults to `dev`, the production box). They
change nothing on the server; never run any other spot target from this skill.

## Step 1: Read the page's numbers

```
make --no-print-directory -C deploy spot-metrics RANGE=24h
```

`RANGE` is one of `1h`, `24h`, `7d`, `30d`, `90d` (default `24h`). It prints, as one JSON document,
exactly what the admin page `/admin/monitoring` shows for that range, computed by the same code:

- `chart_groups`: `host`, `services`, `game`, `sockets`, `traefik`, `storage`, each a list of charts
  with `name`, `unit`, `state`, `latest`, `bucketed` and `retention_days`.
- `games`: games **started** in the range by how they ended, and the completed games' mean, median
  and p90 duration in seconds (`completed_durations` is null without a completed game).
- `live_status`: the game server's `active_games` and `pending_games` now, or `"unavailable"` when it
  did not answer.
- `last_backup_age_seconds`: seconds since the last backup finished, null when unknown.

## Step 2: Read the JSON correctly

- **`state`**: `current` (newest sample at most 3 minutes old), `stale` (older: the collector or its
  source stopped), `never_collected` (no file, table, column or series yet), `unavailable` (the read
  failed). Only `current` describes now; say which state a number came from. Traefik charts take it
  from the newest scrape of any router, so a quiet series (no 5xx yet) is a current 0.
- **`unit`**: the display unit the values are already in: `percent`, `gib`, `mib`,
  `kib_per_second`, `cores` (CPU seconds per second), `count`, `per_second`, `per_minute`,
  `milliseconds`, `seconds`.
- **Null is never zero.** A missing value, an empty bucket and an unknown age are `null`. `latest.value`
  is null when the newest sample gives no reading (a counter's first sample after a restart).
- **`bucketed` is over buckets, not raw samples.** The range is cut into at most 300 buckets; each
  bucket is the mean of its samples (a rate over its interval for counters, the peak for loop lag).
  `mean` and `max` are over the non-empty buckets, so a one-minute spike in a long range is smoothed
  inside its bucket. `empty_buckets` counts buckets with nothing to show: a missed minute, a counter
  reset, or time before collection started. `bucketed` is null for a chart with no data.
- **Traefik keeps 30 days.** For a longer range its charts carry `retention_days: 30`: the older part
  was never collected, not quiet.
- **The `game-ws` numbers are closed connections.** Traefik records a WebSocket request when it ends,
  so `traefik.game_sockets_closed` counts disconnects and `traefik.game_socket_lifetime` is how long
  those sockets lived. Sockets opened per minute are `sockets.connections_accepted`.

## Step 3: Ad-hoc SQL when the report is not enough

```
make --no-print-directory -C deploy spot-metrics-sql SQL="SELECT timestamp, active_games, connections FROM game_status ORDER BY timestamp DESC LIMIT 10"
```

It runs `sqlite3 -readonly -json` on the host's `metrics.db` and prints the rows as JSON (nothing for
no rows) on stdout. It works when the lobby is down. sqlite3 runs in `-safe` mode, and the target
refuses SQL that starts with `.` (a dot-command) or contains a backtick, `$` or `"`: quote strings
with `'` and the `exists` column of `filestat` as `[exists]`.

- Tables: `cpu`, `mem`, `disk`, `net`, `pressure`, `cgroup`, `game_status`, `traefik`, `filestat`,
  `filecount`. `deploy/config/metrics-schema.sql` is the reference for their columns.
- `timestamp` is integer Unix seconds (`datetime(timestamp, 'unixepoch')` to read it). One sample per
  minute per series; rows of different tables are not taken at the same second, so never join on it.
- Totals (CPU time, bytes, messages, `game_status` counters, Traefik counts) only grow until their
  owner restarts: compute rates from neighbouring samples, and treat a change of `boot` (every row) or
  of `game_status.started_at` as a reset, not a drop. A Traefik restart resets its counts with the
  same `boot`: a series exists only after its first request, so one absent at the previous scrape
  counts from zero. A Traefik mean (`_sum` over `_count`) is null for an interval with no requests.
- Rows go back 90 days; `traefik` 30 days.

## Step 4: Report

Answer with the numbers, their units, the range and each chart's state. Flag stale, unavailable or
never-collected sources instead of reading them as zero, and say when a question needs data the
collector does not keep.
