# Backend

Two independent projects, each with its own toolchain, checks and `AGENTS.md`:

* `lobby/` — the Python lobby, a uv project.
* `game_v2/` — the Go game server, a Go module; it imports no Python.

They share the SQLite database, the game ticket secret (the lobby signs tickets, the game server
verifies them) and the internal API secret (the lobby's bearer token on the game server's
credential-returning lookup).

`storage.db`, `data/`, `logs/` and `profiles/` here are the local runtime data of both servers
(gitignored), not source.
