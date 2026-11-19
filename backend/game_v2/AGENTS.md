# Game server (Go)

The game server being ported from `backend/game/` to Go. It is one Go module, outside the uv
project: it imports nothing from `backend/shared/` and the Python tooling does not see it. So far it
holds the engine's base vocabulary, the seam types, its seeded randomness, the wall, shanten, the
hand reading (agari, divider, waits), the hand scoring, the option helpers (a seat's discards,
calls, kans, riichi, furiten and win payments), the round state machine (`engine/internal/round`),
the game played round to round (`engine/internal/game`), the seat record each seat's events keep up
and the seat view it equals (`engine/internal/record`), and the facade over them (`engine/`) with its
seam tests and self-play driver (`seam/`).

## The seam

The module is two sides, a server and an engine, and the engine is reachable only through `engine/`.

* `engine/` is the engine's only public API. The rules live under `engine/internal/`, which the Go
  compiler lets nothing outside `engine/` import, so the server side cannot reach past the facade.
  The facade holds no rule of its own: it wraps `game` and the seed functions of `rng`, and
  re-exports as type aliases the seed and error types a caller builds or matches. No slice it returns shares a backing array
  with the game, so a caller may write into anything it gets; the facade copies what the layer
  below shares, and a seam test writes into every returned slice to hold that.
* The compiler does not stop the opposite direction, so lint rules in `.golangci.yml`, run by
  `make lint-go`, hold it: see Engine purity.
* `engine/tile` is the public vocabulary under the facade: tile kinds, hand tiles, tile ids, winds,
  seats, dice and mpsz notation. It imports nothing of the module, so every engine package can
  build on it. Its exported tables are functions returning arrays, never package `var`s, since any
  importer could write to a public `var`.
* `engine/play` holds every type that crosses the facade: actions, decisions, what the game awaits,
  events with their visibility, refusals, round results, standings, win values and yaku, and the
  seat view. It imports only `engine/tile`, so the server side reads the engine's output without
  reaching under the facade, and every engine package can produce it. gochecksumtype does not see
  through a type alias, so the sum types live here and the facade does not re-export them.
  An absent value is a `play.Option` (a value and an ok flag), never a pointer, so state stays a
  plain value; an absent sum type is nil.
* The server side and `seam/` import `engine`, `engine/play` and `engine/tile`, nothing else of the
  engine; the compiler seals `engine/internal`. depguard holds the vocabulary itself:
  `engine/tile` imports nothing of the module and `engine/play` only `engine/tile`.
* `seam/` is a sibling directory of `engine/` holding tests only. A test package inside `engine/`
  may legally import `engine/internal/...`; a sibling may not, so a test in `seam/` proves a
  behaviour is observable through the facade alone.

## Layers

Imports point one way:

```
cmd -> internal/server -> session -> messaging -> wire -> engine -> engine/internal
```

Inside the engine, `engine/internal/*` packages import `engine/tile`, `engine/play` and each other
along the module graph of mahjong-rs, the port's reference, and never `engine`.

`session`, `messaging` and `wire` do not exist yet. Each is added under `internal/` when the port
gives it work, in this order, never as an empty package. Each `cmd/*` is its own composition root:
its `main` is the only place that reads that binary's flags, environment and signals and wires the
parts it uses, so a tool beside the server builds what it needs without going through
`cmd/gameserver`. `cmd/gameserver` wires the engine into the server once a game message exists.

## Engine purity

The engine is synchronous and deterministic: it does no transport and no I/O, reads no clock, starts
no goroutine and draws randomness only from the seed it is given. The caller holds each `Game`; the
engine keeps no registry and no mutable package-level state. `make lint-go` holds this for non-test
code under `engine/`:

* Imports are an allow-list (`engine-purity`, depguard in strict mode): the engine's own packages and
  a short set of pure standard-library packages. Anything else, the module's `internal/` packages,
  `net`, `os`, `sync`, `math/rand`, the websocket library, fails the lint. When the port needs
  another pure package, add it to the list; an allow entry is a prefix, so end it with `$` to keep
  `math` from admitting `math/rand`.
* `time` is allowed for its types: time crosses the facade as `time.Time` and `time.Duration` values
  the caller passes in. Reading the clock or starting a timer (`time.Now`, `time.Since`,
  `time.Sleep`, `time.After`, tickers) is forbidden by forbidigo, and so is printing.
* Package-level variables and `init` functions are rejected (gochecknoglobals, gochecknoinits),
  except read-only tables. Go has no constant arrays, so a small lookup table is a package-level
  `var` array in a file named `lookup_*.go`, the only engine files gochecknoglobals skips; the
  prefix is one no domain file takes, as `table` would (a table record). Read-only there is a
  review rule, not a lint rule: such a file holds only `var` arrays of values, and no code assigns
  to them. A table too large to write out is a `//go:embed` string, never a `[]byte`, which would be
  mutable state. A table's generator sits beside its package behind `//go:build ignore`.

* No interface abstracts the engine: an interface over it is defined by the server-side package that
  consumes it, when one needs it. The only interfaces the engine declares are sealed sum types,
  since Go has no enum with payloads: an unexported marker method, one struct per variant, and
  `//sumtype:decl` in the interface's doc comment, the only place that directive works.
* A type switch over a sum type and a switch over an enum list every variant, anywhere in the
  module: gochecksumtype and exhaustive both run with `default-signifies-exhaustive: false`, so a
  `default:` branch does not cover the missing ones, and a new variant fails the lint at every switch
  that misses it instead of falling into `default:`. gochecksumtype does not see through a type
  alias, so a package that switches over a sum type imports the package that declares it.
* `Refusal` is a domain outcome, deliberately not an `error`: a player's refused action is an
  expected result. `error` stays for failures that are not one.

## Tests

* Rule unit tests sit beside the code they test, in the `engine/internal/` packages. `seam/` covers
  only behaviour observable through the facade, and does not repeat a rule already pinned below it.
  Server tests sit beside the server code and drive it through `net/http/httptest`, with a real
  WebSocket client for a socket route.
* A game's scenario tests play it through `engine/internal/testkit`, which stages walls and scripts
  actions. testkit is engine code under the coverage gate: it never imports `testing` and never
  asserts, returning values or errors, and it has its own tests. It imports `game`, so only external
  test packages (`package game_test`) use it. A test compares engine states with go-cmp, every
  field exported (`cmp.Exporter`) and empty slices equal to nil.
* Engine state is a value: a slice in it is replaced, never written in place, so a state a caller
  kept stays as it was. A branch test plays two actions from one state and checks the state and
  both branches against fresh replays; one is written for each kind of change that touches a slice.
* Test names follow `Test<Subject>_When<Condition>_Should<Expected>`; drop `When<Condition>` only for
  unconditional behaviour (`TestNewGame_ShouldYieldStartedEventWithFullWall`). One scenario per
  test. The root `AGENTS.md` project rules on what earns a test apply here too.
* `make test-go` gates `engine/...` at 100% of statements. It runs every package with
  `-coverpkg=./engine/...`, so a `seam/` test counts toward engine coverage as much as a test beside
  the code. `bin/check_go_coverage.py` judges the raw profile, block by block, never a rounded
  percentage: a block is covered when any test binary ran it, an uncovered block is printed and
  fails the gate, and so does a profile with no engine block. A block of no statement, such as a sum
  type's empty marker method, has nothing to run and is skipped. The server side is not gated. There
  is no exclusion mechanism: reach the statement or restructure it away.
* A check too slow for every run sits in a `_test.go` file behind a build tag (`exhaustive`), outside
  `make test-go`, and so does one over data kept only on a developer's machine (`tenhou`, the Tenhou
  corpus); its package doc gives the command that runs it. `make lint-go` builds with every tag
  (`run.build-tags`), so the file is type-checked and linted on every run.

## Comments

The commit hook rejects every added comment. In Go that leaves only doc comments on exported
functions, methods and types, the package doc, `//go:` directives and `//nolint:<linter> // reason`.
A sum type's `//sumtype:decl` line belongs to its doc comment. An unexported identifier or a line
inside a function body gets none, and a `_test.go` file gets none at all, so a test's name and its
variables' names carry what it pins. `.golangci.yml` takes no
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
* Go has no release-age setting like the 7-day cooldown uv and npm apply here, so it is a convention.
  Add or upgrade a dependency only at an explicit version published at least 7 days ago:
  `mise exec -- go list -m -json <module>@vX.Y.Z` prints its `Time`, then
  `mise exec -- go get <module>@vX.Y.Z`, one module at a time. Never `go get <module>@latest` or
  `go get -u`, which take a version published minutes ago. A security fix younger than 7 days is the
  one exception, and the commit body says so.
* `make vuln-go` runs govulncheck over the module. It needs the network, so it is not part of
  `make run-all-checks`: run it after adding or upgrading a dependency.
* While iterating, run one package:
  `cd backend/game_v2 && mise exec -- go test ./<pkg> -run <name>`. An engine change runs
  `cd backend/game_v2 && mise exec -- go test -race ./engine/... ./seam/...`: the facade's tests live
  in `seam/`, so `./engine/...` alone skips them.
* The server listens on `127.0.0.1:8712` by default (`-addr`), clear of the Python game server.
