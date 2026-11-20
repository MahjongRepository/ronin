# Game server (Go)

The game server being ported from `backend/game/` to Go. It is one Go module, outside the uv
project: it imports nothing from `backend/shared/` and the Python tooling does not see it. So far it
holds the engine's base vocabulary, the seam types, its seeded randomness, the wall, shanten, the
hand reading (agari, divider, waits), the hand scoring, the option helpers (a seat's discards,
calls, kans, riichi, furiten and win payments), the round state machine (`engine/internal/round`),
the game played round to round (`engine/internal/game`), the seat record each seat's events keep up
and the seat view it equals (`engine/internal/record`), the facade over them (`engine/`) with its
seam tests and self-play driver (`seam/`), the wire format (`internal/wire`), the shaping of the
engine's output into messages and of client messages into actions (`internal/messaging`), the live
games with their sessions (`internal/session`), the rows and replay files it persists beside the
lobby (`internal/store`), its credentials (`internal/auth`), the transport serving the lobby's
routes and the game sockets (`internal/server`) with its composition root (`cmd/gameserver`), the
replay runner (`internal/replay`) with the Go replay check (`cmd/verify`), the Tenhou export
(`internal/tenhou`), the generator of the game client's seat transcripts and replay fixtures
(`cmd/fixtures`), the wall measurement (`cmd/measurewall`), and the one-off migration of the Python
server's data (`internal/migrate`, `cmd/migrate`).

## The seam

The module is two sides, a server and an engine, and the engine is reachable only through `engine/`.

* `engine/` is the engine's only public API. The rules live under `engine/internal/`, which the Go
  compiler lets nothing outside `engine/` import, so the server side cannot reach past the facade.
  The facade holds no rule of its own: it wraps `game`, the seed functions of `rng`, the round a
  seed's wall deals and the lowest shanten the tools' play policies rank by, and re-exports as type
  aliases the seed and error types a caller builds or matches. No slice it returns shares a backing
  array with the game, so a caller may write into anything it gets; the facade copies what the layer
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

`internal/store` and `internal/auth` are leaves beside that line: the session and the server use
`store`, the server alone `auth`, and neither imports anything of the module. `internal/replay` sits
beside `messaging` over the wire: it reads replays for the tools, so the live path never imports it.
`internal/tenhou` sits there too, under the server, which answers the export route with it.
`internal/migrate` sits beside them for `cmd/migrate` alone: it reads old replays through the wire,
checks each rewrite with the Tenhou export and writes through the store, and nothing on the live path
imports it.

Each server package's imports of the module are a depguard rule in `.golangci.yml`: `wire` imports
only `engine`, `engine/play` and `engine/tile`, `messaging` those and `wire`, `session` those,
`messaging` and `store` (never the replay runner), `server` the session, messaging, wire, store,
auth and tenhou but of the engine only `engine/play` and `engine/tile`, `store` and `auth` nothing,
`replay` only the wire and the engine's public packages, `tenhou` only the wire and the seam types,
`migrate` the wire, tenhou, store and the seam types, and each layer added later gets its own. Each
`cmd/*` is its own composition root: its `main` is the only place that reads that binary's flags,
environment and signals and wires the parts it uses, so a tool beside the server builds what it
needs without going through `cmd/gameserver`.
`cmd/gameserver` reads the Python server's environment, wires the store, the session and the
server, and runs the graceful stop (Server).

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
  them (`rewritten/`), which `internal/migrate` produces byte for byte (its tests' `-update` writes
  them; review the diff).

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
* `ReplayLog` is the one collector of a game's replay records, kept by the session and used alike by
  the fixture generator and the replay and Tenhou tests, so what they record is what the server
  saves.

## Session

`internal/session` runs the live games the lobby creates.

* One goroutine owns each game, from its creation to its finalizer: participants and their
  connections, the engine game, the wait, the pause, the timers and the replay records. Sockets,
  timers, lobby calls and AI agent answers reach it only as steps on its channel, one at a time, so
  no step interleaves with another and game state takes no lock. A step never blocks on a client or
  an agent: sends and closes only queue on the `Connection`, and an agent decides on a goroutine of
  its own. Join and Reconnect return once their step ran, bind included, so the socket's next
  message finds its connection bound, and no game step may wait on a socket's reader.
* The `Manager` is the registry: games, tickets, connections and the participant each is bound to,
  behind one mutex. What spans games happens under it in one step: a creation with its checks, an
  end claim releasing the game, its tickets and its connections, a binding against an eviction. No
  step holds it while it waits on a game.
* A timer's firing is a step carrying the token it was armed with, and is dropped when the timer was
  cancelled or re-armed meanwhile: in Go a cancel races its callback. Every time comes from the
  `Clock` (`Config`), virtual in tests through `testing/synctest`.
* The engine stops after a deal, awaiting `play.AwaitingDealt`, and `Begin` makes the dealer's
  first draw. At the game's start the session calls `Begin` only once every seat confirmed the start
  or its timeout confirmed for them, so the start screen shows over the dealt table; the absent
  seats' seat control records go between the deal and the draw, and a reconnect snapshot meanwhile
  is the engine's view of the dealt table, with no decision. A later round's deal and its draw go
  out as one update. Every bank resets on a call that deals.
* A reconnect either takes a seat back from its AI player (seat_control to the others; a turn the
  AI player had not played yet becomes the participant's new decision, keeping the deadline and
  bank of a decision the seat left running, else timed from the reconnect)
  or replaces the participant's still-bound connection, closed with 4002, its wait, timers and
  bank running on. A resync re-sends the same state on the bound connection and changes nothing:
  the snapshot, then the owed decision's opening with how long its timer has run.
* The end is claimed once, in a step: it releases the game from the registry at once and the game's
  goroutine then runs the finalizer (replay save, finish row, closes), each step its own panic
  boundary, so a fault in one still lets every connection close. The start row claims the game id:
  it is written once on the goroutine after the engine game is built and before anything of the
  game is published, and a conflict or a failed write fails the game before play. The finish row is
  written up to three times, 1 s then 2 s apart on the `Clock`, and a cut store context stops the
  waits. Both rows use the store context `New` takes, never a game's.
* `Manager.Settle` waits until every posted step, every agent call and every claimed end's
  finalizer ran. Only a caller that is the session's one source of work may use it: a harness
  driving the session on a Clock whose timers it fires itself, which settles before it reads what
  clients got or moves its clock on.
* A step that fails or panics fails its game, the one server-fault path; a connection's failed step
  that did not seat it is closed with 1011 on its own.
* The session owns the seed and the roster. It draws each game's seed and seats the participants by
  the seed's seat permutation, by input order, never by name; the engine gets only the seed. A
  participant is keyed by its ticket for the whole game and seated once, at the start, and its turn
  timer lives as long as it does, so its bank survives a disconnect.
* A seat with no connected participant is an AI player's, answered through the engine like a
  participant's answer, by `Config.Agent` (by default its decision's default: it never wins, calls or
  declares). The game asks one AI decision at a time, a call's AI callers in seat order and an AI
  turn after the AI turn delay, so a human sees AI turns one at a time; the agent decides off the
  game's goroutine and its answer comes back as a step. Every engine call, a take-back of the asked
  seat and the end drop the request, and an answer to a dropped one is ignored. An agent error, no
  answer within the base turn time or an action the decision does not offer plays the default,
  with a warning; an agent panic, a refused offered answer or a refused default or timeout default
  is a server fault.
  When no connected participant remains the game is abandoned, so a game is never all AI players.
  Every handover, either way, writes the replay's seat control record and sends seat_control to the
  connected participants ahead of the moves that follow.
* A user plays a game from its creation, pending included, until its end is claimed or Shutdown
  empties the registry, disconnected or not: the lobby's per-user lookup and the refusal of a user
  already playing answer from this. A pending game starts once everyone joined, or at its timeout
  with AI players in the absent seats; with nobody connected it is abandoned and records nothing.
  The lobby's withdrawal ends a pending game nobody joined, and a withdrawn id is refused for a
  ticket's lifetime (24 h).
* A connection must authenticate (JOIN_GAME or RECONNECT) within the auth timeout or be closed. A
  connection the server closes leaves the registry in the same step, so a pipelined join cannot pick
  it up, and a message arriving on it afterwards gets no answer. A participant's newest connection
  wins: the bound one is closed with 4002, which the client treats as terminal, and a connection
  already bound is refused before anyone is replaced.
* Every game action echoes the wait id stamped on the message that opened the participant's
  decision. The id advances only when a new wait, or a pause opening with it, opens a decision for
  that connected participant, or a reconnect takes back its AI player's turn; it survives
  replacements and reconnects. A wait is kept, sending no opening and re-timing nothing, only while
  its kind is unchanged and it awaits only seats that held their decision before the call: a partial
  call answer keeps the other callers', a kan's replacement draw opens a new one. A seat not awaited
  and an id not its latest get the same stale-action error and touch neither the engine nor a timer,
  so a guessed id reveals no hidden wait; a call answer naming another tile than the open call's is
  refused by the session.
* A refusal is the session's policy: a rule judgment, or an action the engine does not await now,
  answers a game error and the decision, its id and its timer go on; structurally impossible input
  (not offered, a tile not held) closes that human with 1008 and seats an AI player.
* The engine's awaited seats drive the timers, never the events: a new wait re-arms them for its
  connected seats, a kept one stops only the actor's. A timeout plays the seat's default action as
  its own answer. Turns and calls draw from one bank after their free base time, and ending a wait
  charges every running decision, a call another seat resolved included. Both pauses, the start
  confirm and the round advance, go on once every seat that owed its confirmation (its connected
  participants when the pause opened) confirmed, timed out or left; any other action in a pause is
  stale. A round end's pause waits its timeout once per result the client shows, so a double ron
  waits twice. `DefaultTiming` holds the values.
* The finish row is built whole from the start row, never from engine or connection state at the
  end, and the first finish wins; a game that never started, or whose start row was refused,
  records none and saves no replay, so it never touches another game's row or replay file. The
  replay holds the engine's events only, each draw once and no opening or notice, plus the seat
  control records: a seat with no connection at the start is `absent` between the deal and the
  dealer's draw, a leave is `left` ahead of its AI player's moves, a take-back is a human return,
  and a replacement or an AI player seated from the start writes none. An abandoned game's replay
  is discarded; a failed replay save or a finish write failing every attempt turns the end into a
  failure (1011).
* Each step logs as its own subject: every line of a game carries `game_id`, and a line about a
  seated participant its `seat`. The messages the log gates match are named constants with the
  Python server's text and level. Concealed hand tiles are logged at DEBUG only, and game tickets
  never at INFO or above.
* Shutdown ends no game. A graceful stop ends games only through the disconnect of each socket the
  server closed; `Shutdown`, called after that, lets a still-registered game vanish with no finish row and
  waits for the finalizers and store writes.

## Server

`internal/server` serves the lobby's REST routes, `/health`, `/status` and `WS /ws/{game_id}`.

* The server owns each socket: one goroutine reads it, rate-limits and decodes each frame and
  hands the message to the session, one writes its queue, and one pings it. The session sees it only
  as a `session.Connection`, so it holds no socket state.
* A decoded message past the rate limit and the answers before routing (ping, the resync budget)
  goes through the `Router`, which parses it, verifies a join's or reconnect's ticket and calls the
  session. It takes any `session.Connection`, so a harness with no socket routes through the same
  code.
* The REST answers keep the Python server's status codes, JSON keys and error texts, and the
  lobby's creation body is read as strictly as Python's model read it: exactly its keys, no field
  of another JSON type, lengths in characters. A socket whose path holds an invalid game id is
  refused with 403 before the handshake, as uvicorn answered Python's close before accept.
* `/status` is a contract: Telegraf's `fieldinclude` allow-list and its metrics schema store its
  keys, the lobby reads its game counts, and counter-reset detection keys on `started_at`, the
  process start in whole epoch seconds, so counters stay cumulative. A test holds the keys against
  `deploy/config/telegraf.conf`. `loop_lag_max_ms` is the per-game queue delay the session measures:
  the longest a routed message waited for its game to take it in the last minute, null without one.
* A graceful stop keeps Python's order inside compose's 15 s grace period, on one deadline: the
  HTTP server stops taking connections, `Server.Shutdown` closes every socket with 1012 and waits
  until each ran its disconnect, then shuts the session down, which drains the finalizers and the
  store writes, and the database closes last. Past the deadline the sockets still open are dropped
  and the store's context is cancelled.

## Replay

`internal/replay` plays a replay this server wrote again through the engine, for the replay check
and the fixture tools.

* A replay records events, not actions, so the loader derives the actions: a discard or declared
  meld is its seat's, a round end names its winners, head-bumped ron seats, kyuushu declarer and
  triple ron declarers, and every other call answer was a pass, which the runner plays itself for
  the seats a prompt still awaits. A recorded event the engine refuses to reproduce fails the run;
  there is no lenient mode. A closed kan's record holds no copy its declarer named, which only a
  robbing ron's winning tile shows, so the loader names that copy for a robbed closed kan and the
  lowest one for any other.
* Only this server's rules profile loads: a replay rewritten from `0.4-dev` was scored under older
  rules and does not reproduce. A replay holds its seed and no wall, so a game staged on fixed
  walls runs again only from its own setup.
* `cmd/verify` checks a game's stored replay, not its row: it requires the game end, records the
  run through a fresh `messaging.ReplayLog` with the stored names and AI flags under the requested
  game id, and compares every record but seat control byte for byte with the stored ones, so a
  wrong draw, discard or meld fails as much as a wrong score, and so does a replay copied under
  another id. `bin/verify_games.py --go-verify` runs it per game after the script's own row
  check, which is how `make run-games SERVER=go` verifies its games.

## Tenhou export

`internal/tenhou` writes a stored replay as a tenhou.net mjlog for the lobby's Tenhou download.

* It reads the records alone and never runs the engine, so a replay of either rules profile converts,
  a rewritten `0.4-dev` one included: the rewritten robbed-kan replay converts to the log the Python
  export wrote from the original, and a test holds that. The one difference is the INIT dice, which
  a Tenhou log stores less one (0 to 5) and the Python export wrote as thrown.
* Every seat moves to Tenhou's as it is read: Tenhou seats its first dealer at 0, so its seat order is
  the dealer order and each INIT's round counter counts the dealer rotations.
* A ron writes one AGARI per win, each from the scores the win before it left, as Tenhou does: the
  riichi sticks on the first win's `ba`, the honba on every win's, a winner's melds newest first.
* A replay with no game end has no log, and a record the log cannot be written from fails the export;
  neither ever answers a partial log.

## Seat transcripts

`cmd/fixtures` plays the seat scenarios through the real session and `Router` on virtual time and
writes what each named seat's client met, the game client's end-to-end pin of the session.

* Time moves only between steps: every timer due by a step's moment fires at its own moment in the
  order it was armed, and the harness settles the session after each firing and each step. A step
  falls on a multiple of 250 ms and never on the moment a timer fires, so every time, bank and
  elapsed value is exact and two runs write the same bytes.
* A scenario stages its first rounds' walls; a fixed wall source ends the game once its walls are
  dealt, so every later round is the seed's own wall for its round number and dealer, laid out as a
  fixed wall. A later round's dealer is known only once it is dealt, so a scenario runs again with
  the dealers it saw until they match. Fixed walls throw (1, 1), so a later round's dice are not the
  seed's.
* A transcript is the JSON the Python generator wrote (one event per line, keys sorted, Python's
  number and string forms), so the client reads either.

## Replay fixtures

`cmd/fixtures` also writes the replay files the game client's replay tests and storybook read. One
run writes or checks both sets: `make generate-fixtures` and the `make fixtures-check` gate.

* A replay scenario plays the engine directly, one engine call at a time, and records each call
  through `messaging.ReplayLog` as the session would: absent seats' seat control records between
  the deal and the dealer's draw, an AI player's seat answered from its decision's default at once
  in the awaited order, and a leave or a return as its own record. A staged game stages its first
  round and deals every later one from the seed as the seat scenarios do; the other games are dealt
  from their seed and played to their end by a fixed policy, the default action or the eager one
  that wins whenever offered and otherwise discards towards ready by `engine.Shanten`.
* Each replay must end in the outcome its scenario names and reproduce its game through
  `internal/replay` from the same setup before it is written; a cut falls between engine calls, as
  the server saves only between steps, and must still load and run.

## Wall measurement and profiles

`cmd/measurewall` is `make measure-wall SERVER=go`, the port of the Python wall measurement over the
facade's seed functions.

* Its engine seeds and control shuffle come from a port of Python's `random.Random` seeded with the
  script's strings, so for the same arguments it measures the same walls and prints the same report,
  and either side reads the other's JSON as a baseline. `testdata/python_report.txt` is the Python
  script's report, and a test holds the Go one to it.
* `make profile SERVER=go` profiles `BenchmarkRun_FullGame` (`internal/replay`), the replay of the
  client's Go full game fixture; `make profile-games SERVER=go` runs `cmd/gameserver -cpuprofile`.

## Migration

`cmd/migrate` is run once, by hand, with both servers stopped: it rewrites every stored `0.4-dev`
replay into the current version and converts every `played_games` row's final scores to tenths.

* A rewritten replay is the game as it was played and scored: it keeps rules profile 1 and every record
  the new format did not reshape keeps its bytes. What the rewrite adds is derived from the old records
  and checked against them: a robbed kan's meld goes right after the declarer's last record, ahead of
  any seat control line, and pao is assigned by the call rule both servers apply, which must agree with
  every win's pao seat.
* Lossless or untouched: a record or field `0.4-dev` never held, records that contradict what the
  rewrite derives, a rewrite the codec refuses, or one of an ended game that converts to no Tenhou log
  leaves the file as it was and fails the run. A replay cut inside a record is the one partial rewrite:
  its records before the cut, counted apart.
* Idempotent by construction: a replay at the current version is skipped, and a row is converted only
  while it lacks the tenths marker, which every row Go writes carries, so no row is multiplied twice
  whatever order the runs and the server take. The rows convert in one transaction, and a dry run rolls
  it back and writes no replay.

## Security requirements

Mandatory for all server-side code; review must catch violations.

* Every WebSocket frame is charged to the connection's rate limit after decoding and before
  processing, so malformed frames count too: an over-budget malformed frame gets no reply or log,
  and consecutive undecodable frames (non-binary included) close the connection. A resync, which
  costs a whole snapshot, draws on a far tighter budget of its own.
* A ticket's game must match the path's game id, and the path's game id is validated
  (`store.IsValidGameID`) before the handshake. The socket has no Origin check: the ticket
  authenticates, and the dev hosts the client runs on would fail an origin pattern.
* A REST route that returns a credential (the participant ticket lookup), spends real CPU on a
  request (the Tenhou export) or ends a game on the lobby's word (the withdrawal) answers only the
  internal API secret as a bearer token, compared in constant time (`auth.IsInternalBearer`); a
  credential's answer is `Cache-Control: no-store`. In development the server's CORS lets the
  lobby origin's scripts read its GETs, so its bind address is no isolation.
* `/status` answers without auth, so it carries only process-wide totals since start and gauges,
  never per-user data.
* A REST body is read through a hard size cutoff (`http.MaxBytesReader`), never whole and unbounded.
* Every goroutine has an owner and an error boundary: one serving a game fails that game, any other
  logs and closes. The server owns each socket's writer goroutine, so the session holds no socket
  state: 256 queued messages, a 10 s send deadline, the socket terminated on overflow, the close
  frame the last item. Sends and closes never block or fail on a dead or slow socket; a dead socket
  surfaces only at receive, where the disconnect seats an AI player.
* No panic from handling a message leaves its handler: one that reaches a game fails that game,
  any other closes the socket as an internal error (1011).
* Liveness is the server's own WebSocket ping (20 s interval, 20 s timeout). A client's PING is only
  a latency probe: it is answered with a pong once it passes the rate limit, before routing,
  authenticated or not, and touches no session.
* Every socket's read limit is the decoder's buffer limit (`wire.MaxMessageBytes`), set before the
  first read, since a socket takes frames before it authenticates; an oversized frame closes the
  connection with 1009.
* A message that fails validation is answered and logged with only its error type, never its input
  or the decoder's text, which can quote the input.

## Persistence and credentials

The lobby reads what the game server writes, and signs what it verifies, so both packages keep the
Python server's formats.

* The SQLite file is shared. The game server creates only `played_games` and its index, in the
  lobby's DDL; the lobby creates its own tables when it opens the file. Opening sets the file and
  its WAL and SHM siblings to 0600. A row's time columns are Python's `isoformat()` (`+00:00`,
  microseconds only when nonzero), the same instants in `data` end in `Z`, and `data` is the JSON
  the lobby's `PlayedGame` validates: seat order at the start, placement order at a completed end.
  `testdata/python_rows.json` holds rows Python wrote, and Go must write them byte for byte but for
  `final_score_unit`: every row Go writes ends with that key (`store.FinalScoreUnit`), its final scores
  in tenths. A row without it holds the Python server's whole points until the migration converts it.
* A game's row is its id's durable claim: the start insert keeps an existing row and returns
  `store.ErrGameRecorded`, so once a game's start row is written its id is never played again. A
  game that wrote none (abandoned or withdrawn while pending, or refused by the engine) leaves its id
  free.
* At startup, once its listener is bound, the server closes every row with no end as `error`, as
  `RecordFailed` would: no game survives a restart, so such a row is a game a crash or a shutdown
  left unfinished. This holds only while exactly one game server writes a database
  (`AUTH_DATABASE_PATH`): a second server on another address would have its live games closed, and
  nothing guards that; the bind only stops a second launch on the same address before the sweep.
* Replay files keep their layout, gzip, owner-only modes and 1 MiB read cap; every path goes
  through an `os.Root`, so no id or link leaves the replay directory.
* A ticket verifies only as the lobby signs one: padded base64url (padding required, the URL
  alphabet), exactly the four fields, `expires_at` a JSON float. `testdata/lobby_tickets.json`
  holds tickets the lobby's code signed and the verdict Python reached on each. An empty secret
  verifies nothing.

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
  expected result. `error` stays for failures that are not one. A state the rules say cannot
  happen, such as the scorer rejecting an offered hand for anything but no yaku, a settled win for
  any reason, or a payment that does not fit its win, panics with `play.EngineFaultError` and is
  never returned; the session's step guard turns it into a failed game.
* `wall.Wall` and `round.CallPrompt` mix receiver kinds on purpose: their readers take the value,
  since callers chain them on non-addressable returns (`g.round.Wall().DoraIndicators()`,
  `g.round.Prompt().Value.Offers(seat)`), and their mutators take a pointer on a held copy.

## Tests

* Rule unit tests sit beside the code they test, in the `engine/internal/` packages. `seam/` covers
  only behaviour observable through the facade, and does not repeat a rule already pinned below it.
  Server tests sit beside the server code and drive it through `net/http/httptest`, with a real
  WebSocket client for a socket route; a test of a ping, a budget or a strike limit shortens the
  `SocketConfig` rather than waiting.
* mahjong-rs is the reference for every rule and event order, and `seam/` holds the proof: it replays
  games mahjong-rs dumped (`seam/testdata/README.md`) through the facade and the ported driver, and
  every decision, action and event must match line for line. A change to a rule or to what the
  engine emits and when follows mahjong-rs and regenerates that set there, never the other way.
  The sanctioned divergences keep that set passing unchanged: `Begin` makes the dealer's first draw
  as its own call, where mahjong-rs draws with the deal, and the scorer rejecting an offered hand
  for anything but no yaku, a settled win for any reason, or a payment that does not fit its win,
  panics with `play.EngineFaultError`.
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
* `internal/wire` has fuzz targets for the live and replay decoders: whatever a decoder accepts must
  re-encode to stable bytes. `internal/messaging` fuzzes `ParseClientMessage` over decoded input: it
  parses or refuses with an `InvalidMessageError`. `go test` replays only their seeds (the goldens,
  the rewritten replays and encoded client messages). Mutation runs take every core, so they are by
  hand only, after a codec or parser change, capped, and their corpus is never committed:
  `go test -run '^$' -fuzz '^FuzzDecode_' -fuzztime=30s -parallel=2 ./internal/wire`, for replays
  `go test -run '^$' -fuzz '^FuzzDecodeReplay_' -fuzztime=30s -parallel=2 ./internal/wire`, and for the
  parser `go test -run '^$' -fuzz '^FuzzParseClientMessage_' -fuzztime=30s -parallel=2 ./internal/messaging`.

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
  and, with the compiler, stands in for a typecheck target; `make test-go` runs the server side
  (`cmd/`, `internal/`) under the race detector, then every test in shuffled order with coverage
  and no race detector, then the coverage gate, each pass with a two-minute timeout. The race pass
  leaves out the engine and `seam/`, which start no goroutine and are its slowest packages under
  `-race`; it keeps Go's test cache, while the shuffled pass always runs, so a test reading a file
  outside the module (the Python goldens, `telegraf.conf`), which the cache does not track, still
  runs every time. Coverage under `-race` counts atomically and costs several times both passes.
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
* The server listens on `127.0.0.1:8712` by default (`-addr`).
* `make run-game-v2-docker` builds the server's own image and starts it as the local `game-v2`
  service; `make stop-game-v2-docker` stops it. Neither `release.yml` nor `deploy/docker-compose.yml`
  knows it. The image is built from the repo root with its own `Dockerfile.dockerignore`, so the
  production `deploy/Dockerfile` and the root `.dockerignore` stay untouched; the build refuses a Go
  other than `mise.toml`'s, and bakes in the version and commit, since a Docker build has no VCS
  stamp. The local compose runs it as the host user, because the dev database and the replays are
  owner-only and the host's lobby reads both, and mounts the whole `backend/` directory, not the
  database file, so SQLite's WAL and SHM siblings are the files the host's lobby uses. The container
  holds `:8712`, the port `make run-local-server` and `make run-games SERVER=go` start their own Go
  server on, and neither can kill the root-owned port holder: their `DOCKER=1` modes run this
  container in its place (`GAME_V2_LOG_LEVEL` overrides the log level `.env.local` sets), and
  otherwise it must be stopped first.
