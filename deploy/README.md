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

Disables SSH password authentication, installs Docker, configures the firewall (UFW + iptables DOCKER-USER chain), and sets up restic backups with a daily timer.

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
make spot-provision TARGET=<target>        # SSH hardening, Docker, firewall, backups
make spot-deploy TARGET=<target>           # pull image, restart services
make spot-backup TARGET=<target>           # run a manual backup
make spot-backup-list TARGET=<target>      # list backup snapshots
make spot-restore TARGET=<target>          # restore from latest snapshot
make spot-restore TARGET=<target> SNAPSHOT=<id>  # restore specific snapshot
make spot-run TASK=<task> TARGET=<target>  # run any spot task by name
```

## SSH authentication

The Makefile auto-detects SSH agent in this order:

1. `SSH_KEY=~/.ssh/id_rsa` -- explicit key file (if set)
2. `~/.1password/agent.sock` -- 1Password SSH agent (if socket exists)
3. System `ssh-agent` -- fallback
