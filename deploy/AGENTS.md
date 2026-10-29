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
  an error-log grep, and backup, restore and download-backup tasks.
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
* Per-service settings live in compose `environment:`, secrets only in `.env`. A deployment-specific
  setting has no default (`backend/AGENTS.md`), so a new one must be added here or the service fails
  to start and the deploy's health gate stops. A release that adds, renames or removes a required
  setting needs the new image and the new compose together: ship it with `spot-deploy`, which uploads
  compose and pulls in one task, never `spot-update` or the box's `make update`, which pull the new
  image under the old compose. Rolling such a release back needs the old compose too.
* Lobby and game share one SQLite DB under `/opt/ronin/data/db/`.

## Logs and backups

* Containers log to **journald** only; there are no application log files on the server. The
  Makefile's log-check target pulls errors to the workstation.
* A daily systemd timer backs up the database and replays with restic to a repository on the
  **same host**, so a backup does not survive the loss of the box (`README.md`).
