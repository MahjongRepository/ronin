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

### 3. Run setup

```
cd deploy
make spot-setup TARGET=<target>
```

This runs four tasks in order:

1. **setup-ssh** -- disables SSH password authentication, key-only access
2. **setup-docker** -- installs Docker from the official apt repository (skips if already installed)
3. **setup-firewall** -- configures UFW, restricts Docker to HTTP/HTTPS only via iptables DOCKER-USER chain
4. **setup-app** -- creates `/opt/ronin/` directory structure, copies `.env.example` as `.env`

### 4. Configure secrets

SSH into the server and edit `/opt/ronin/.env`:

```
AUTH_GAME_TICKET_SECRET=<generate a random secret>
ACME_EMAIL=<your email for Let's Encrypt>
```

## Deploying changes

CI builds and pushes the Docker image to GHCR. Deploys pull the latest image and restart services.

```
cd deploy
make spot-deploy TARGET=<target>
```

This uploads config files, renders templates (substitutes `%%DOMAIN%%`), pulls the latest image, and starts services with `docker compose up -d --remove-orphans`. Only containers whose image or config changed are recreated -- there is no pre-emptive `docker compose down`.

Health checks verify lobby (:8710), game (:8711), and traefik are running.

If a deploy changes service names or port bindings, run `docker compose down` on the server manually first.

## Running individual tasks

```
cd deploy
make spot-run TASK=<task-name> TARGET=<target>
```

Available tasks: `setup-ssh`, `setup-docker`, `setup-firewall`, `setup-app`, `deploy`.

## SSH authentication

The Makefile auto-detects SSH agent in this order:

1. `SSH_KEY=~/.ssh/id_rsa` -- explicit key file (if set)
2. `~/.1password/agent.sock` -- 1Password SSH agent (if socket exists)
3. System `ssh-agent` -- fallback
