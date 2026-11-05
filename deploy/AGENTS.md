# Deploy conventions

The production deploy layer: a [spot](https://github.com/umputun/spot) playbook (`spot.yml`) and a
production `docker-compose.yml` (Traefik + lobby + game) under `/opt/ronin/` on the server, run from
a workstation through `make -C deploy <target> TARGET=<env>` (`TARGET` picks `spot-env.<env>.yml`,
which holds the domain). `README.md` is the runbook for a new server and lists the targets.

## Architecture

* `.github/workflows/release.yml` is the **only** path that builds the image (`Dockerfile`) and
  pushes it to GHCR as a public package. The deploy Makefiles have no build or push target, and the
  deploy has no `docker login`.
* `.github/workflows/create-release.yml` cuts a release from a version and a summary: it pushes
  `release`, tags and publishes the GitHub release, bumps `main` to the next minor, then calls
  `release.yml` for the image. A push made with `GITHUB_TOKEN` starts no workflow, so the call is
  the only thing that builds a release cut this way.
* `Makefile` wraps spot: one-time bootstrap and provisioning tasks, the deploy, service control,
  an error-log grep, the read-only metrics report and SQL, and backup, restore and download-backup
  tasks.
* `Makefile.server` is uploaded to `/opt/ronin/Makefile` on every deploy for manual control on the
  box; the spot service-control tasks call its targets.

## Conventions

* **Image is hardcoded** in `docker-compose.yml`, no image or tag variables. `APP_VERSION` and
  `GIT_COMMIT` are baked in at build time; never set them in compose or `.env`.
* **Setup once, deploy many.** Bootstrap creates `/opt/ronin/.env` (app secrets) and `.env.system`
  (backup secret) from the `.env*.example` files; deploy never touches them. A key added to an example
  reaches only a fresh server — add it to the server file by hand.
* **Templates, not generated configs.** The deploy uploads `docker-compose.yml` and
  `config/traefik-dynamic.yml` and substitutes `%%DOMAIN%%`, failing if a placeholder survives.
  Bind-mounted configs are rendered with `sed ... >` rather than `sed -i`, which would replace the
  inode under the running container's mount.
* **Deploy never goes through `down`.** `docker compose up -d --remove-orphans` recreates only the
  changed services; a change to service names or port bindings needs a manual `down` first. The
  deploy gates on both services' `/health` and a running Traefik.
* **Bounded shutdown.** Both uvicorn commands pass a graceful-shutdown timeout (uvicorn otherwise
  waits forever for a client whose transport is stalled), and `stop_grace_period` leaves room after
  it for the lifespan shutdown and the database drain before docker's SIGKILL.
* **Liveness is the WebSocket protocol ping.** Both uvicorn commands (and `bin/run-local-server.sh`)
  pin the `--ws` ping flags; the apps run no ping of their own, so removing the flags leaves dead
  sockets open.
* **Frame size is capped before buffering.** Both uvicorn commands (and `bin/run-local-server.sh`)
  pin `--ws-max-size`: uvicorn otherwise buffers a 16 MiB frame before the app's own size checks
  run, and game sockets accept frames before they authenticate. The game cap is the decoder's
  `MAX_BUFFER_LEN`, the lobby's twice its room message limit; keep each in step with that limit.
  An oversized frame closes the socket with 1009. TestClient bypasses uvicorn, so no test pins this.
* **No WebSocket compression.** Both uvicorn commands (and both local launchers in `bin/`) pass
  `--ws-per-message-deflate false`: frames average about 13 bytes, so deflate costs CPU per frame
  and saves nothing, and with it off browsers get what the bot client (which never offers it) gets,
  so bot runs measure production's send path.
* **HTTP compression is Traefik's.** The `compress-text` middleware (`config/traefik-dynamic.yml`)
  compresses an allowlist of static text types (JS, CSS, SVG, XML) and sits only on the routers
  serving them, never the WebSocket ones; the apps add no GZip middleware. HTML and JSON stay out of
  the allowlist (BREACH): pages carry a CSRF token beside reflected input, bot API answers carry keys.
  A response the app already encodes (the gzip replay files) passes through as is.
* Immutable asset caching applies only to the Vite-generated `assets/` directories of the lobby
  and game client, whose filenames contain content hashes. Entry HTML, manifests and public files
  outside those directories must not receive that policy.
* Per-service settings live in compose `environment:`, secrets only in `.env`. A deployment-specific
  setting has no default (`backend/AGENTS.md`), so a new one must be added here or the service fails
  to start and the deploy's health gate stops. A release that adds, renames or removes a required
  setting needs the new image and the new compose together: ship it with `spot-deploy`, which uploads
  compose and pulls in one task, never `spot-update` or the box's `make update`, which pull the new
  image under the old compose. Rolling such a release back needs the old compose too.
* Lobby and game share one SQLite DB under `/opt/ronin/data/db/`.
* **One cgroup slice per service.** Each compose service sets its own `cgroup_parent`
  (`ronin-<service>.slice`), so the host collector finds every container's CPU, memory and OOM
  numbers at `/sys/fs/cgroup/ronin.slice/ronin-<service>.slice/` (systemd reads `-` in a slice name
  as nesting). A new service gets its own slice.
* **Traefik's metrics port is loopback-only.** The Prometheus endpoint has its own `metrics`
  entrypoint, published on `127.0.0.1:8082` for the host collector; it must never get a router or a
  public binding.

## Metrics collector

* **A host timer, not a container.** `ronin-metrics.timer` runs `scripts/collect-metrics.sh` every
  minute, which runs Telegraf `--once` with `config/telegraf.conf`. Provisioning installs it
  (`setup-monitoring`: the checksum-pinned release binary, never the `.deb`, which enables a daemon);
  `spot-monitoring` re-applies binary, config, script and units. `spot-deploy` never touches it.
* **Agents read metrics through two read-only tasks.** `metrics-report` runs
  `backend/scripts/monitoring_report.py` in the lobby container, the page's own assembly, so its JSON
  matches `/admin/monitoring`; `metrics-sql` runs `sqlite3 -readonly` on the host, so it works when
  the lobby is down. Both are block scripts, so spot echoes `/bin/sh -c <file>`, which the make
  targets drop with spot's `[host] > ` prefix to print bare JSON. A value passed with `-e` lands in
  a double-quoted `export`, so it cannot hold `"` or `$`.
* `metrics.db` lives in `/opt/ronin/data/metrics/`, is written only by the collector, and is not
  backed up. Every path and URL in the config and script is an environment variable with the
  production default, so the same files run locally against `make run-local-server`.
* **The schema is a contract.** `config/metrics-schema.sql` is the captured `.schema` of a run that
  exercised every source, and the lobby reader relies on it. A change to the config, the inputs'
  field lists or the Telegraf version means repeating the local proof (the collector run against
  `make run-local-server`, a local Traefik with the compose metrics flags and containers started
  with `--cgroup-parent=ronin-<service>.slice`) and refreshing that file. Telegraf's `.schema` text order is not deterministic, so compare it semantically: run
  this on the server's DB and on a DB built with `sqlite3 fixture.db < config/metrics-schema.sql`,
  then diff the two outputs.

  ```sql
  SELECT 'col', m.name, c.name, c.type FROM sqlite_master m, pragma_table_info(m.name) c
    WHERE m.type = 'table' UNION ALL
  SELECT 'idx', m.name, l.name, group_concat(i.name, ',' ORDER BY i.seqno) FROM sqlite_master m,
    pragma_index_list(m.name) l, pragma_index_info(l.name) i WHERE m.type = 'table'
    GROUP BY m.name, l.name ORDER BY 1, 2, 3;
  ```
* Why each workaround exists, since neither file carries comments:
  * `table_update_template`: Telegraf creates a table from the first row it writes, so a later row
    with a new column (`loop_lag_max_ms` is `null` until the first lag sample, a missing file has no
    size) would fail the write.
  * `batch_transactions`: without it the output commits row by row, so a reader could see part of a
    Traefik scrape, and a failed write could leave one for good; the lobby reads a series missing
    from a scrape as an exporter restart and would count its whole total again on the next one.
  * `time_*` only for `cpu`: the `usage_*` row is a half-row over a 500 ms window; the reader
    computes usage from the cumulative times.
  * Every input lists exactly the fields the reader uses (`fieldinclude`, never `fieldpass`), so the
    schema does not follow the kernel or a plugin's additions; a filter that removes every field
    drops the metric, which is how `kernel` keeps only its `pressure` rows.
  * Integer timestamps (`_time_integer_format=unix`): SQLite's date functions return NULL for
    Telegraf's text timestamp form.
  * The `boot` tag on every row (the wrapper exports `BOOT`, the first 8 characters of the kernel
    boot id): a reset identity, because tables carry slightly different timestamps and cannot be
    joined by time. `omit_hostname` keeps a constant tag out; `boot` is in the Traefik `taginclude`
    because that filter would otherwise drop the global tag too.
  * `--strict-env-handling`: an unset `${VAR}` without a default stays literal, so every variable
    the config needs either has a `${VAR:-default}` or is exported by the wrapper (`BOOT`,
    `METRICS_DB`).
  * The journal-mode open before Telegraf (`PRAGMA journal_mode=DELETE`): rollback mode is what the
    lobby's read-only mount can read (WAL needs a writable `-shm`), and opening the database first
    recovers a half-written transaction.
  * The script, not Telegraf, owns indexes and retention (90 days, `traefik` 30), and runs them
    even when collection fails.

## Logs and backups

* Containers log to **journald** only; there are no application log files on the server. The
  Makefile's log-check target pulls errors to the workstation.
* A daily systemd timer backs up the database and replays with restic to a repository on the
  **same host**, so a backup does not survive the loss of the box (`README.md`).
