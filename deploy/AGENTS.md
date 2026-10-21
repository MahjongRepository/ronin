# Deploy conventions

The production deploy layer: a [spot](https://github.com/umputun/spot) playbook (`spot.yml`) and a
production `docker-compose.yml` (Traefik + lobby + game) under `/opt/ronin/` on the server, run from
a workstation through `make -C deploy <target> TARGET=dev` (`TARGET` picks `spot-env.<TARGET>.yml`).
`README.md` is the runbook for a new server.

## Architecture

* `.github/workflows/release.yml` is the **only** path that builds the image (`deploy/Dockerfile`,
  frontend + Python deps + trimmed Alpine runtime, non-root `app`, no CMD — compose supplies the
  uvicorn command per service) and pushes it to GHCR as a public package. The deploy Makefiles have no
  image build or push target, and the deploy has no `docker login`.
* `Makefile` wraps spot: `spot-bootstrap` (base packages, `/opt/ronin` dirs, `.env` and `.env.system`
  from their examples), `spot-provision` (`setup-ssh`, `setup-docker`, `setup-firewall`,
  `setup-restic`, `setup-journald`), `spot-deploy`, `spot-update` / `spot-stop` / `spot-restart` /
  `spot-down` / `spot-status`, `spot-check-logs-errors [SINCE=...]`, `spot-backup`,
  `spot-backup-list`, `spot-restore [SNAPSHOT=<id>]`, `spot-download-backup` (restores into the
  local `backend/storage.db` and `backend/data/replays/`) and `spot-run TASK=<task>`.
* `Makefile.server` is uploaded to `/opt/ronin/Makefile` on every deploy for manual control on the
  box (`update`, `stop`, `restart`, `down`, `status`, `logs`, `shell`).

## Conventions

* **Image is hardcoded**: `ghcr.io/mahjongrepository/ronin:latest` in `docker-compose.yml`, no image
  or tag variables. `APP_VERSION` and `GIT_COMMIT` are baked in at build time; never set them in
  compose or `.env`.
* **Setup once, deploy many.** Bootstrap creates `/opt/ronin/.env` (`AUTH_GAME_TICKET_SECRET`,
  `ACME_EMAIL`, `LOG_LEVEL`) and `.env.system` (`RESTIC_PASSWORD`) from the examples; deploy never
  touches them. A key added to an example reaches only a fresh server — add it to the server file by
  hand.
* **Templates, not generated configs.** The deploy uploads `docker-compose.yml`, `config/servers.yaml`
  and `config/traefik-dynamic.yml` and substitutes `%%DOMAIN%%` with `sed`, failing if a placeholder
  survives. Bind-mounted configs are rendered with `sed ... >` rather than `sed -i`, which would
  replace the inode under the running container's mount.
* **Deploy never goes through `down`.** `docker compose up -d --remove-orphans` recreates only the
  changed services; a change to service names or port bindings needs a manual `down` first. The
  deploy gates on lobby `:8710/health`, game `:8711/health` and a running Traefik.
* Per-service settings live in compose `environment:` (`AUTH_*`, `LOBBY_*`, `GAME_*`,
  `LOG_FORMAT: json`), secrets only in `.env`. A deployment-specific setting has no default
  (`backend/AGENTS.md`), so a new one must be added here or the service fails to start and the
  deploy's health gate stops. Lobby and game share one SQLite DB at `/opt/ronin/data/db/ronin.db`.

## Logs and backups

* Containers log to **journald** (`setup-journald`: persistent, 500 MB, 30 days); there are no application
  log files on the server. `make -C deploy spot-check-logs-errors SINCE="2 hours ago"` greps app errors
  and tracebacks and saves them to `/tmp/ronin-errors.log` on the workstation.
* `setup-restic` installs a persistent daily systemd timer (04:00 plus up to 10 minutes of jitter)
  running `scripts/backup.sh`: an
  `sqlite3 .backup` of the DB plus the replays into a restic repository at `/opt/ronin/backups/` on
  the same host.
