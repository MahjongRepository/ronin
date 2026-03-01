# Deploy

Server provisioning and deployment using [spot](https://github.com/umputun/spot).

Tested on Ubuntu 24.04 LTS only.

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

Installs base packages (`micro`, `kitty-terminfo`), creates the `/opt/ronin/` directory structure, and copies `.env.example` as `.env` and `.env.system.example` as `.env.system`.

### 4. Configure secrets

SSH into the server and edit `/opt/ronin/.env`:

```
AUTH_GAME_TICKET_SECRET=<generate a random secret>
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

Disables SSH password authentication, installs Docker, configures the firewall (UFW + iptables DOCKER-USER chain), sets up restic backups with a daily timer, and configures journald for persistent log storage.

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

## Commands

All commands run from `deploy/` and require `TARGET=<target>`.

```
make spot-bootstrap TARGET=<target>        # base packages, dirs, env templates
make spot-provision TARGET=<target>        # SSH hardening, Docker, firewall, backups, journald
make spot-deploy TARGET=<target>           # pull image, restart services
make spot-update TARGET=<target>           # pull latest images, restart changed services
make spot-stop TARGET=<target>             # stop all services (containers preserved)
make spot-restart TARGET=<target>          # restart all services
make spot-down TARGET=<target>             # stop and remove all containers
make spot-status TARGET=<target>           # show service status
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

The Makefile auto-detects SSH agent in this order:

1. `SSH_KEY=~/.ssh/id_rsa` -- explicit key file (if set)
2. `~/.1password/agent.sock` -- 1Password SSH agent (if socket exists)
3. System `ssh-agent` -- fallback
