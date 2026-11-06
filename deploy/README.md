# Deploy

Server provisioning and deployment using [spot](https://github.com/umputun/spot).

Tested on Ubuntu 24.04 LTS and Debian 13.

## Prerequisites

- [spot](https://github.com/umputun/spot) installed locally
- SSH key access to the target server (root)

## New server setup

One-time provisioning that installs Docker, configures the firewall, and prepares the application directory.

### 1. Add the server target

Add a new target in `spot.yml`:

```yaml
targets:
  prod:
    hosts:
      - {host: "1.2.3.4", name: "prod-server"}
```

### 2. Create the environment file

Create `spot-env.<target>.yml` with the domain for this environment:

```yaml
DOMAIN: ronin.example.com
```

### 3. Bootstrap the server

```
cd deploy
make spot-bootstrap TARGET=<target>
```

Applies pending OS updates, turns on automatic security updates, installs base packages (`micro`, `kitty-terminfo`), creates the `/opt/ronin/` directory structure, and copies `.env.example` as `.env` and `.env.system.example` as `.env.system`. If it prints `REBOOT REQUIRED` (a new kernel), reboot the server before provisioning.

### 4. Configure secrets

SSH into the server and edit `/opt/ronin/.env`:

```
AUTH_GAME_TICKET_SECRET=<generate a random secret>
AUTH_INTERNAL_API_SECRET=<generate another random secret>
ACME_EMAIL=<your email for Let's Encrypt>
```

Edit `/opt/ronin/.env.system`:

```
RESTIC_PASSWORD=<generate a random password for restic backups>
```

### 5. Provision the server

```
cd deploy
make spot-provision TARGET=<target>
```

Disables SSH password authentication, installs Docker, configures the firewall (UFW + iptables DOCKER-USER chain), sets up restic backups with a daily timer, installs the metrics collector, and configures journald for persistent log storage.

## Deploying changes

CI builds and pushes the Docker image to GHCR. Deploys pull the latest image and restart services.

```
cd deploy
make spot-deploy TARGET=<target>
```

This uploads config files, renders templates (substitutes `%%DOMAIN%%`), pulls the latest image, and starts services with `docker compose up -d --remove-orphans`. Only containers whose image or config changed are recreated -- there is no pre-emptive `docker compose down`.

Health checks verify lobby (:8710), game (:8711), and traefik are running.

If a deploy changes service names or port bindings, run `docker compose down` on the server manually first.

## Backups

Restic backs up SQLite databases and game replays to a local repository at `/opt/ronin/backups`.

SQLite databases are safely snapshotted using `sqlite3 .backup` before each backup run.

A daily systemd timer runs at 04:00 (with 10min jitter). Retention policy: 7 daily, 4 weekly, 3 monthly.

### Manual backup

```
make spot-backup TARGET=<target>
```

### List snapshots

```
make spot-backup-list TARGET=<target>
```

### Restore from latest snapshot

```
make spot-restore TARGET=<target>
```

### Restore a specific snapshot

```
make spot-restore TARGET=<target> SNAPSHOT=<snapshot-id>
```

Restore stops the lobby and game containers, copies data from the snapshot, removes WAL/SHM files, fixes file ownership, and restarts services. Let's Encrypt certs are not backed up — Traefik re-obtains them automatically.

## Monitoring

Provisioning installs a host metrics collector: Telegraf 1.40.3 (the release binary, checksum-pinned in `spot.yml`) run once a minute by `ronin-metrics.timer` through `/opt/ronin/scripts/collect-metrics.sh`. It samples host CPU, memory, disk, network and pressure, each service's cgroup slice, the game server's `/status`, Traefik's loopback metrics endpoint (`127.0.0.1:8082`), the database and replay sizes, and the last backup time, into `/opt/ronin/data/metrics/metrics.db` (90 days; Traefik 30 days). The database is not backed up.

`spot-deploy` does not touch the collector. After changing `config/telegraf.conf`, `scripts/collect-metrics.sh` or the `ronin-metrics` units, re-apply them:

```
make spot-monitoring TARGET=<target>
```

Check it on the server with `systemctl list-timers ronin-metrics.timer` and `journalctl -u ronin-metrics.service`.

Read the numbers without a browser: `make spot-metrics TARGET=<target> RANGE=24h` prints what `/admin/monitoring` shows for the range as JSON (run inside the lobby container), and `make spot-metrics-sql TARGET=<target> SQL="SELECT ..."` runs a read-only query on `metrics.db` from the host, so it works when the lobby is down. sqlite3 runs in `-safe` mode, and the target refuses SQL that starts with `.` (a dot-command) or contains a backtick, `$` or `"`; quote strings with `'`. With `make -C deploy`, add `--no-print-directory` so stdout is the bare JSON.

The collector only sees the box from inside. Point an external uptime service at the lobby's public `https://<domain>/health`: it proves the box, Traefik and the lobby are up, not the game server.

## Commands

All commands run from `deploy/` and require `TARGET=<target>`.

```
make spot-bootstrap TARGET=<target>        # OS updates, base packages, dirs, env templates
make spot-provision TARGET=<target>        # SSH hardening, Docker, firewall, backups, metrics collector, journald
make spot-monitoring TARGET=<target>       # install or update the metrics collector (binary, config, script, timer)
make spot-deploy TARGET=<target>           # pull image, restart services
make spot-update TARGET=<target>           # pull latest images, restart changed services
make spot-stop TARGET=<target>             # stop all services (containers preserved)
make spot-restart TARGET=<target>          # restart all services
make spot-down TARGET=<target>             # stop and remove all containers
make spot-status TARGET=<target>           # show service status
make spot-metrics TARGET=<target> RANGE=24h      # monitoring page data as JSON (1h, 24h, 7d, 30d, 90d)
make spot-metrics-sql TARGET=<target> SQL="..."  # read-only query on metrics.db, rows as JSON
make spot-backup TARGET=<target>           # run a manual backup
make spot-backup-list TARGET=<target>      # list backup snapshots
make spot-restore TARGET=<target>          # restore from latest snapshot
make spot-restore TARGET=<target> SNAPSHOT=<id>  # restore specific snapshot
make spot-run TASK=<task> TARGET=<target>  # run any spot task by name
```

## Manual server control

A `Makefile` is deployed to `/opt/ronin/` for direct use when SSH'd into the server:

```
cd /opt/ronin
make update    # pull latest images, restart changed services
make stop      # stop all services (containers preserved)
make restart   # restart all services
make down      # stop and remove all containers
make status    # show service status
make logs      # follow service logs
```

The spot tasks (`spot-update`, `spot-stop`, etc.) call the same server Makefile targets remotely.

## Logging

All container logs (app output + crash traces + OOM kills) go to journald via Docker's `journald` logging driver. journald provides persistent storage, time-based querying, and automatic rotation (500MB max, 30-day retention).

### Querying logs

```bash
# Follow all ronin logs
journalctl CONTAINER_TAG=ronin -f

# Lobby logs from last 24 hours
journalctl CONTAINER_NAME=ronin-lobby-1 --since "1 day ago"

# Errors only from last day
journalctl CONTAINER_NAME=ronin-lobby-1 --since "1 day ago" -p err

# Game server logs for a specific date range
journalctl CONTAINER_NAME=ronin-game-1 --since "2026-03-01" --until "2026-03-02"

# Export as JSON
journalctl CONTAINER_TAG=ronin --since "1 day ago" -o json --no-pager
```

`docker compose logs` and `make logs` still work as before.

### Local development

For file-based logs during local development, set environment variables:

```bash
export LOBBY_LOG_DIR=backend/logs/lobby
export GAME_LOG_DIR=backend/logs/game
```

When these are unset (or empty), app-level file logging is disabled and logs go to stdout only.

## SSH authentication

Spot authenticates with a key file, `~/.ssh/id_ed25519` by default; pass `SSH_KEY=<path>` to use
another one. No SSH agent is used.
