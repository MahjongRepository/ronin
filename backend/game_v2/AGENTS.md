# Game server (Go)

The game server being ported from `backend/game/` to Go. It is one Go module, outside the uv
project: it imports nothing from `backend/shared/` and the Python tooling does not see it. So far it
holds the engine's base vocabulary, the seam types, its seeded randomness, the wall, shanten, the
hand reading (agari, divider, waits), the hand scoring, the option helpers (a seat's discards,
calls, kans, riichi, furiten and win payments), the round state machine (`engine/internal/round`),
the game played round to round (`engine/internal/game`), the seat record each seat's events keep up
and the seat view it equals (`engine/internal/record`), the facade over them (`engine/`) with its
seam tests and self-play driver (`seam/`), the wire format (`internal/wire`), and the shaping of the
engine's output into messages and of client messages into actions (`internal/messaging`).

## The seam

The module is two sides, a server and an engine, and the engine is reachable only through `engine/`.

* `engine/` is the engine's only public API. The rules live under `engine/internal/`, which the Go
  compiler lets nothing outside `engine/` import, so the server side cannot reach past the facade.
  The facade holds no rule of its own: it wraps `game` and the seed functions of `rng`, and
  re-exports as type aliases the seed and error types a caller builds or matches. No slice it
  returns shares a backing array with the game, so a caller may write into anything it gets; the
  facade copies what the layer below shares, and a seam test writes into every returned slice to
  hold that.
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

`session` does not exist yet; it is added under `internal/` when the port gives it work, never as an
empty package. `wire`'s and `messaging`'s imports of the module are depguard rules in
`.golangci.yml`: `wire` imports only `engine`, `engine/play` and `engine/tile`, `messaging` those
and `wire`, and each layer added later gets its own. Each `cmd/*` is its own composition root: its
`main` is the only place that reads that binary's flags, environment and signals and wires the parts
it uses, so a tool beside the server builds what it needs without going through `cmd/gameserver`.
`cmd/gameserver` wires the engine into the server once a game message exists.

## The wire

`internal/wire` is the format the server, the replay tools and the clients read, so its bytes are
a contract.

* A message or replay record is a `wire.Map`, an ordered list of keyed values, never a Go map: its
  keys encode in the order it lists them. An integer takes the fewest bytes, a float is always a
  float64 (so `Int(20)` and `Float(20)` differ on the wire), strings use str8 from 32 bytes, and
  binary data appears only as a replay's seed. Score maps and the replay's rules envelope are the
  only string-keyed maps.
* Keys, event codes and result codes are only ever added: a retired one leaves its gap, never a
  reused number. The live and replay key sets and the replay schema (the fields each record and
  result type requires, and each field's type) live beside the codec, which checks them on encode
  and decode alike; the size, length and map limits bound decoding only, as they did in Python.
* A change to the replay format bumps `wire.ReplayVersion`; a replay names the rules profile it was
  played under, this server's or the one every rewritten `0.4-dev` game keeps.
* `internal/wire/testdata/` holds the goldens a Go test owns (`go test ./internal/wire -update`
  rewrites their bytes and key names from their payloads; review the diff), the `0.4-dev` replays
  that are the one home of the old-format inputs (`legacy/`), and the expected output of rewriting
  them (`rewritten/`), which the one-off migration must produce byte for byte.

## Messaging

`internal/messaging` is the only place the engine's vocabulary meets the wire's.

* The engine emits facts only. Every field a message names beyond them comes from the session (the
  roster, wait ids, timers, the pause) or is derived from the engine's output (a win's points,
  honba bonus, collected sticks, per-yaku han and pao share; a game end's leftover sticks), never
  from engine state. A round end and a game end take their table context from a seat's record once
  the call's events are applied.
* A decision's opening is built from the `play.Decision` alone and the reconnect snapshot from a
  seat's `play.SeatRecord` alone, so a live wait and its re-send match and the wire never follows the
  engine's internals. Engine refusals map to the wire's own game error codes; a refusal no client
  builds has none.
* The wire tells an integer from a float. A time whose wire type follows its value (the bank, a
  pause's timeout) is a `messaging.Seconds`, whole or fractional; a time the wire always carries as
  a float (timer settings, the pending game timeout, elapsed times) is a `float64`.
* A round end's scores are those before its payments; its score changes take them to the scores
  after it.

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
* mahjong-rs is the reference for every rule and event order, and `seam/` holds the proof: it replays
  games mahjong-rs dumped (`seam/testdata/README.md`) through the facade and the ported driver, and
  every decision, action and event must match line for line. A change to a rule or to what the
  engine emits and when follows mahjong-rs and regenerates that set there, never the other way.
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
* `make test-go` gates `engine/...` and `internal/wire` at 100% of statements. It runs every
  package with `-coverpkg=./engine/...,./internal/wire/...`, so a `seam/` test counts toward engine
  coverage as much as a test beside the code. `bin/check_go_coverage.py` judges the raw profile,
  block by block, never a rounded percentage: a block is covered when any test binary ran it, an
  uncovered block is printed and fails the gate, and so does a profile with no block of either gated
  directory. A block of no statement, such as a sum type's empty marker method, has nothing to run
  and is skipped. The rest of the server side is not gated. There is no exclusion mechanism: reach
  the statement or restructure it away.
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
