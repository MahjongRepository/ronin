# Game server (Go)

The game server being ported from `backend/game/` to Go. It is one Go module, outside the uv project:
it imports nothing from `backend/shared/` and the Python tooling does not see it. So far it holds
the structure the port fills, not the game: the facade's `NewGame`, `Act`, `Event`, `Action` and
`Refusal`, the 136-tile wall count behind them and their seam tests are placeholders, replaced by the
first ported behaviour.

## The seam

The module is two sides, a server and an engine, and the engine is reachable only through `engine/`.

* `engine/` is the engine's only public API. The rules live under `engine/internal/`, which the Go
  compiler lets nothing outside `engine/` import, so the server side cannot reach past the facade.
* The compiler does not stop the opposite direction, so lint rules in `.golangci.yml`, run by
  `make lint-go`, hold it: see Engine purity.
* `seam/` is a sibling directory of `engine/` holding tests only. A test package inside `engine/`
  may legally import `engine/internal/...`; a sibling may not, so a test in `seam/` proves a
  behaviour is observable through the facade alone. It imports nothing of the module but `engine`.

## Layers

Imports point one way:

```
cmd -> internal/server -> session -> messaging -> wire -> engine -> engine/internal
```

`session`, `messaging` and `wire` do not exist yet. Each is added under `internal/` when the port
gives it work, in this order, never as an empty package. `cmd/gameserver` is the composition root:
the only place that reads flags and signals, and the place the engine is wired into the server once
a game message exists.

## Engine purity

The engine is synchronous and deterministic: it does no transport and no I/O, reads no clock, starts
no goroutine and draws randomness only from the seed it is given. The caller holds each `Game`; the
engine keeps no registry and no package-level state. `make lint-go` holds this for non-test code
under `engine/`:

* Imports are an allow-list (`engine-purity`, depguard in strict mode): the engine's own packages and
  a short set of pure standard-library packages. Anything else, the module's `internal/` packages,
  `net`, `os`, `sync`, `math/rand`, the websocket library, fails the lint. When the port needs
  another pure package, add it to the list; an allow entry is a prefix, so end it with `$` to keep
  `math` from admitting `math/rand`.
* `time` is allowed for its types: time crosses the facade as `time.Time` and `time.Duration` values
  the caller passes in. Reading the clock or starting a timer (`time.Now`, `time.Since`,
  `time.Sleep`, `time.After`, tickers) is forbidden by forbidigo, and so is printing.
* Package-level variables and `init` functions are rejected (gochecknoglobals, gochecknoinits).

* The engine exports concrete types, not interfaces. An interface over the engine is defined by the
  server-side package that consumes it, when one needs it.
* `Refusal` is a domain outcome, deliberately not an `error`: a player's refused action is an
  expected result. `error` stays for failures that are not one.

## Tests

* Rule unit tests sit beside the code they test, in `engine/internal/rules` and deeper engine
  packages. `seam/` covers only behaviour observable through the facade, and does not repeat a rule
  already pinned below it. Server tests sit beside the server code and drive it through
  `net/http/httptest`, with a real WebSocket client for a socket route.
* Test names follow `Test<Subject>_When<Condition>_Should<Expected>`; drop `When<Condition>` only for
  unconditional behaviour (`TestNewGame_ShouldYieldStartedEventWithFullWall`). One scenario per
  test. The root `AGENTS.md` project rules on what earns a test apply here too.
* `make test-go` gates `engine/...` at 100% of statements. It runs every package with
  `-coverpkg=./engine/...`, so a `seam/` test counts toward engine coverage as much as a test beside
  the code. `bin/check_go_coverage.py` judges the raw profile, block by block, never a rounded
  percentage: a block is covered when any test binary ran it, an uncovered block is printed and
  fails the gate, and so does a profile with no engine block. The server side is not gated. There is
  no exclusion mechanism: reach the statement or restructure it away.

## Comments

The commit hook rejects every added comment. In Go that leaves only doc comments on exported
functions, methods and types, the package doc, `//go:` directives and `//nolint:<linter> // reason`.
An unexported identifier or a line inside a function body gets none, and a `_test.go` file gets none
at all, so a test's name and its variables' names carry what it pins. `.golangci.yml` takes no
comments either: a forbidigo pattern's `msg` is where its reason goes.

## Tooling

* Go and golangci-lint are pinned in the repo-root `mise.toml`, and `go.mod`'s `go` line matches the
  pinned Go. The Makefile puts both on `PATH` for its own targets only, so a `go` command typed
  outside `make` goes through `mise exec --`.
* `make format-go` rewrites files (gofumpt, goimports, gci import groups); `make lint-go` fails on an
  untidy `go.mod` (`go mod tidy -diff`), then runs golangci-lint, which also reports formatting diffs
  and, with the compiler, stands in for a typecheck target; `make test-go` runs every test under the
  race detector in shuffled order with a two-minute timeout, then the coverage gate.
* Fix a lint finding rather than silence it. A suppression is `//nolint:<linter> // reason` on the
  narrowest line; nolintlint rejects one without a named linter or a reason. Never loosen
  `.golangci.yml` to get green.
* `make vuln-go` runs govulncheck over the module. It needs the network, so it is not part of
  `make run-all-checks`: run it after adding or upgrading a dependency.
* While iterating, run one package:
  `cd backend/game_v2 && mise exec -- go test ./<pkg> -run <name>`. An engine change runs
  `cd backend/game_v2 && mise exec -- go test -race ./engine/... ./seam/...`: the facade's tests live
  in `seam/`, so `./engine/...` alone skips them.
* The server listens on `127.0.0.1:8712` by default (`-addr`), clear of the Python game server.
