# Game server (Go)

The game server: the engine under `engine/`, the server side and its tools under `internal/` and `cmd/`. The
sections below say which package owns which concern; `engine/internal/record` is the seat record and view,
`internal/pyjson` the Python-style JSON the lobby's files use.

## The seam

The module is two sides, a server and an engine, and the engine is reachable only through `engine/`.

* `engine/` is the engine's only public API. The rules live under `engine/internal/`, which the Go
  compiler lets nothing outside `engine/` import, so the server side cannot reach past the facade.
  The facade holds no rule of its own. Every slice it returns is the caller's own: a new method
  copies what the layer below shares, and `TestGame_WhenACallerWritesIntoEverySliceItReturns_ShouldStayAsItsTwin`
  (`seam/engine_test.go`) must cover it.
* The compiler does not stop the opposite direction, so lint rules in `.golangci.yml`, run by
  `make lint-go`, hold it: see Engine purity.
* `engine/tile` is the public vocabulary under the facade: tile kinds, hand tiles, tile ids, winds,
  seats, dice and mpsz notation. It imports nothing of the module, so every engine package can
  build on it. Its exported tables are functions returning arrays, never package `var`s, since any
  importer could write to a public `var`.
* `engine/play` holds every type that crosses the facade (its package doc). gochecksumtype does not
  see through a type alias, so the sum types live here and the facade does not re-export them. An
  absent value is a `play.Option`, never a pointer, so state stays a plain value.
* `seam/` is a sibling directory of `engine/` holding tests only. A test package inside `engine/`
  may legally import `engine/internal/...`; a sibling may not, so a test in `seam/` proves a
  behaviour is observable through the facade alone.

## Layers

Imports point one way:

```
cmd -> internal/server -> session -> messaging -> wire -> engine -> engine/internal
```

Inside the engine, `engine/internal/*` packages import `engine/tile`, `engine/play` and each other,
never `engine`.

`internal/store`, `internal/replayfile` and `internal/pyjson` are leaves beside that line;
`internal/replay`, `internal/tenhou` and `internal/migrate` sit beside `messaging` over the wire,
and the live path never imports `replay` or `migrate`. No lint rule covers `cmd/`: keep
`cmd/verify` off `store` so it links no database driver. `internal/tenhou/tenhoulog` settles
Tenhou's rounds through the facade, so the engine holds no Tenhou format of its own.

Each server package's imports of the module are a depguard rule in `.golangci.yml`, whose `desc` gives the
reason; a new layer gets its own rule. Each
`cmd/*` is its own composition root: its `main` is the only place that reads that binary's flags,
environment and signals and wires the parts it uses, so a tool beside the server builds what it
needs without going through `cmd/gameserver`.
`cmd/gameserver` reads the settings environment the lobby shares (`bin/local-settings.sh` locally).

## The wire

`internal/wire` is the format the server, the replay tools and the clients read, so its bytes are
a contract.

* A message or replay record is a `wire.Map`, never a Go map, so its keys encode in the order it
  lists them. Decoders outside this module read these bytes (`frontend/game_v2/src/shared/protocol/wire-codec.ts`,
  the bots), so the forms `encode.go` writes and what `validate.go` admits change only together with them.
* Keys, event codes and result codes are only ever added: a retired one leaves its gap, never a
  reused number. The key sets and the replay schema are `key.go` and `replay_schema.go`.
* A change to the replay format bumps `wire.ReplayVersion`.
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
* A hand shown at a round's end goes out sorted by id (the hand order rule under Session). A decision's
  opening follows every event of its call, a seat's furiten change included.
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
  behind one mutex that only its own methods take. What spans games happens under it in one step: a
  creation with its checks, an end claim releasing the game, its tickets and its connections, a
  binding against an eviction. No step holds it while it waits on a game.
* A timer's firing is a step carrying the token it was armed with, and is dropped when the timer was
  cancelled or re-armed meanwhile: in Go a cancel races its callback. Every time comes from the
  `Clock` (`Config`), virtual in tests through `testing/synctest`.
* The engine stops after a deal, awaiting `play.AwaitingDealt`, and `Begin` makes the dealer's
  first draw. At the game's start the session calls `Begin` only once every seat confirmed the start
  or its timeout confirmed for them, so the start screen shows over the dealt table.
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
  game is published, and a conflict or a failed write fails the game before play.
* `Manager.Settle` waits until every posted step, every agent call and every claimed end's
  finalizer ran. Only a caller that is the session's one source of work may use it: a harness
  driving the session on a Clock whose timers it fires itself, which settles before it reads what
  clients got or moves its clock on. Under it the agent must answer without waiting: an agent call
  waiting on anything, its ctx included, holds Settle, since the agent's deadline fires only when
  the harness moves the clock.
* A step that fails or panics fails its game, the one server-fault path; a connection's failed step
  that did not seat it is closed with 1011 on its own.
* The session owns the seed and the roster. It draws each game's seed and seats the participants by
  the seed's seat permutation, or, created with `fixed_seats`, in wind order from the seed's first
  dealer, by input order either way, never by name (`docs/rng.md`); the engine gets only the seed. A
  participant is keyed by its ticket for the whole game and seated once, at the start, and its turn
  timer lives as long as it does, so its bank survives a disconnect.
* A seat with no connected participant is an AI player's, answered through the engine like a
  participant's answer, by `Config.Agent` (by default its decision's default: it never wins, calls
  or declares). The game waits for one AI answer at a time, a call's AI callers in seat order and an
  AI turn after the AI turn delay, so a human sees AI turns one at a time; the agent decides off the
  game's goroutine and its answer comes back as a step. One agent serves every game and a dropped
  request's call may still run beside the next, so the agent is called concurrently. Every engine
  call, a take-back of the asked seat and the end drop the request, and an answer to a dropped one
  is ignored. An agent error, no answer within the base turn time or an action the decision does not
  offer plays the default, with a warning; an agent panic, a refused offered answer or a refused
  default or timeout default is a server fault. When no connected participant remains the game is
  abandoned, so a game is never all AI players. Every handover, either way, writes the replay's seat
  control record and sends seat_control to the connected participants ahead of the moves that
  follow.
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
  connected seats, a kept one stops the timers of all seats whose decisions have closed. A call
  settles once no seat still owed can change its outcome (`engine.Game.Outranked`): an outranked
  caller keeps its prompt, timer and bank charge and its answer is taken, so nothing it sees
  shows that a ron is still owed, and it learns the outcome with everyone. An outranked AI seat is
  never asked, and a kept wait keeps the request of an AI seat that still decides. An answer
  already in flight to a call that timed out or settled without the seat is an ordinary race,
  dropped with a debug line, never answered or logged as stale; the seat also gets `call_closed`
  when its prompt would otherwise stay up, the call still open or its outcome held. The claimer itself sees its claim wait only on
  an outstanding ron, an accepted tell since pace outranks timing tells. A
  timeout plays the seat's default action as its own answer. Turns and calls draw from one bank after their free base time, and ending a wait
  charges every running decision, a call another seat resolved included. Both pauses, the start
  confirm and the round advance, go on once every seat that owed its confirmation (its connected
  participants when the pause opened) confirmed, timed out or left; any other action in a pause is
  stale. A round end's pause waits its timeout once per result the client shows, so a double ron
  waits twice. `DefaultTiming` holds the values.
* The consequences of a discard, and of a closed or added kan, are held (`Config.DiscardHold`, nil
  for none): the discard goes out at once with the kan dora it reveals, the kan with no dora, every
  furiten change at once whichever call answer brings it, and so does a call's prompt with its
  timer, but the next draw, a call's outcome, a riichi deposit and the round's end wait until the
  hold and the call window have both ended. An accepted call response from a connected client
  (including an automatic pass) shortens the hold to its floor (`discardHoldFloor`) from the original discard or kan.
  A server AI decision, timeout, stale action or resync leaves the sampled deadline in place.
  A leave or a reconnect while the game end is held hands no seat over and records no seat control
  (the returning seat's own snapshot alone shows it played by itself):
  the game ends completed at the hold's deadline, or at once when its last connected participant
  leaves. The replay takes the whole call's records at once, so seat control records keep their place after them, but the engine
  is past what the clients saw, so nothing reads it for a client meanwhile: a game action is stale,
  an AI player is not asked, and a snapshot is the last update shown plus the events shown since
  (`engine.Follow`), with no decision. The next wait opens, and its timers start, only when the
  held events are shown, and no seat's bank pays for the hold. The hold's randomness is the
  process's, never the game seed's. `cmd/gameserver` holds discards even with one human at the table; local mode (Security requirements),
  the fixtures and the benchmarks hold none.
* What a seat sends must not show the table its hand order, which is the sorted deal with every
  draw appended. The session shows a call's furiten changes ahead of its other consequences, held
  or not, so their order never tells a seat whether its pass was the last answer. With
  `Config.Pick` (nil plays everything as named) it plays a pon, a chi and a closed kan with copies
  picked among those that look the same (`engine.Game.Disguised`), since a client names the first
  copies in hand order, and after a seat's own chi or pon a timeout or an AI player's default
  discards a picked legal tile, never the last in hand order. `cmd/gameserver` always picks at
  random, from the process, never the game seed; the fixtures and the benchmarks pick nothing.
* The finish row is built whole from the start row, never from engine or connection state at the
  end, and the first finish wins; a game that never started, or whose start row was refused,
  records none and saves no replay, so it never touches another game's row or replay file. The
  replay holds the engine's events only, each draw once and no opening or notice, plus the seat
  control records: a seat with no connection at the start is `absent` between the deal and the
  dealer's draw, a leave is `left` ahead of its AI player's moves, a take-back is a human return,
  and a replacement or an AI player seated from the start writes none. An abandoned game's replay
  is discarded; a failed replay save or a finish write failing every attempt turns the end into a
  failure (1011).
* A playing game keeps an observer timeline: the replay's records in their order, append-only, each
  batch stamped once with the `Clock` when the replay collected it. It shares the replay's own
  records, which nothing writes to, except the game start, stored as a copy without the seed, so
  nothing an observer reads can hold the seed. Each value has one lock owner: the timeline's mutex
  guards its records and its seal, the Manager's guards the registry of timelines and their
  expiry, and neither is taken under the other. The end claim seals it for every reason, the release sets its expiry, and a read serves only
  the records older than the delay, off the game's goroutine.
* Each step logs as its own subject: every line of a game carries `game_id`, and a line about a
  seated participant its `seat`. The messages the log gates match are named constants with fixed
  text and level. Concealed hand tiles are logged at DEBUG only, and game tickets
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
* The REST answers have the status codes, JSON keys and error texts the lobby reads, and the
  lobby's creation body is read strictly: exactly its keys, no field of another JSON type, lengths in
  characters. A socket whose path holds an invalid game id is refused with 403 before the handshake.
* `/status` is a contract: Telegraf's `fieldinclude` allow-list and its metrics schema store its
  keys, the lobby reads its game counts, and counter-reset detection keys on `started_at`, the
  process start in whole epoch seconds, so counters stay cumulative. A test holds the keys against
  `deploy/config/telegraf.conf`.
* `/status` carries no per-user data. The list of games playing (`GET /games`) names players, East
  to North from the first dealer as the lobby shows them, so it answers only the internal secret;
  so does the observe route, which names them too.
* A graceful stop runs on one deadline (`shutdownTimeout`, `cmd/gameserver/main.go`), which must fit
  compose's 15 s `stop_grace_period` (`deploy/docker-compose.yml`); `docs/architecture.md` gives its order.

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
  another id. `bin/verify_games.py` runs it per game after the script's own row
  check, which is how `make run-games` verifies its games.

## Tenhou export

`internal/tenhou` writes a stored replay as a tenhou.net mjlog for the lobby's Tenhou download.
It owns the Tenhou ids: each yaku's, the dora counts' and the limit codes.

* It reads the records alone and never runs the engine, so a replay of either rules profile converts,
  a rewritten `0.4-dev` one included: the rewritten robbed-kan replay converts to the log recorded in `testdata` from the
  original, and a test holds that.
* Every seat moves to Tenhou's as it is read: Tenhou seats its first dealer at 0, so its seat order is
  the dealer order and each INIT's round counter counts the dealer rotations.
* A ron writes one AGARI per win, each from the scores the win before it left, as Tenhou does: the
  riichi sticks on the first win's `ba`, the honba on every win's, a winner's melds newest first.
* A replay with no game end has no log, and a record the log cannot be written from fails the export;
  neither ever answers a partial log.

## Seat transcripts

`cmd/fixtures` plays the seat scenarios through the real session and `Router` on virtual time and
writes what each named seat's client met, the game client's end-to-end pin of the session.

* A scenario stages its first rounds' walls; a fixed wall source ends the game once its walls are
  dealt, so every later round is the seed's own wall for its round number and dealer, laid out as a
  fixed wall. A later round's dealer is known only once it is dealt, so a scenario runs again with
  the dealers it saw until they match. Fixed walls throw (1, 1), so a later round's dice are not the
  seed's.

## Replay fixtures

`cmd/fixtures` also writes the replay files the game client's replay tests and storybook read. One
run writes or checks both sets: `make generate-fixtures` and the `make fixtures-check` gate.

* A replay scenario plays the engine directly (`cmd/fixtures/replays.go`, `replay_scenarios.go`) and
  records each call through `messaging.ReplayLog` as the session would.
* Each replay must end in the outcome its scenario names and reproduce its game through
  `internal/replay` from the same setup before it is written; a cut falls between engine calls, as
  the server saves only between steps, and must still load and run.

## Wall measurement and profiles

`cmd/measurewall` is `make measure-wall`, the wall measurement over the facade's seed functions.

* Its engine seeds and control shuffle come from a port of Python's `random.Random` seeded with fixed
  strings, so the same arguments measure the same walls and print the same report. `testdata/python_report.txt`
  holds the reference report, and a test holds the Go one to it.
* `make profile`'s benchmarks are `BenchmarkRun_FullGame` (`internal/replay`) and
  `BenchmarkRouter_FullGame` and `BenchmarkSocket_FullGame` (`internal/server`). Each driver's pin
  test requires the session to save the fixture's exact replay, so they cannot drift into another
  game. `cpu-ns/op` (process CPU per game, clients included) is the number a socket change moves.
  They play one table at a time, so contention between games shows only in `make profile-games`.
* The layer table charges each CPU sample to the deepest frame of this module's packages, so library
  and runtime work counts toward its caller, except GC work (background marking, assists, sweeping,
  scavenging), which gets its own row.
* Regenerate `cmd/gameserver/default.pgo` (`make update-pgo`) after a large change to the hot path. Test
  binaries ignore it unless built with `-pgo`, which is why the profile scripts pass it.

## Migration

`cmd/migrate` is run once, by hand, with both servers stopped: it rewrites every stored `0.4-dev`
replay into the current version and converts every `played_games` row's final scores to tenths.

* A rewrite is lossless or leaves the file untouched and fails the run, and a rerun converts nothing
  twice (`internal/migrate`); a change to it keeps both properties.

## Security requirements

Mandatory for all server-side code; review must catch violations.

* Every WebSocket frame is charged to the connection's rate limit after decoding and before
  processing, so malformed frames count too: an over-budget malformed frame gets no reply or log,
  and consecutive undecodable frames (non-binary included) close the connection. A resync, which
  costs a whole snapshot, draws on a far tighter budget of its own.
* The server runs in production mode unless its environment names local mode, which only the bot
  runs (`bin/run-bots-games.sh`) set, and an unknown mode refuses to start: local mode raises the
  message budget so four bots at a table are never throttled, holds no discard (Session), and
  changes nothing else. `make run-local-server` runs production mode.
* A ticket's game must match the path's game id, and the path's game id is validated
  (`replayfile.IsValidGameID`) before the handshake. The socket has no Origin check: the ticket
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
  state: a bounded queue and send deadline, the socket terminated on overflow, the close
  frame the last item. Sends and closes never block or fail on a dead or slow socket; a dead socket
  surfaces only at receive, where the disconnect seats an AI player.
* No panic from handling a message leaves its handler: one that reaches a game fails that game,
  any other closes the socket as an internal error (1011).
* Liveness is the server's own WebSocket ping (`DefaultSocketConfig`). A client's PING is only
  a latency probe: it is answered with a pong once it passes the rate limit, before routing,
  authenticated or not, and touches no session.
* Every socket's read limit is the decoder's buffer limit (`wire.MaxMessageBytes`), set before the
  first read, since a socket takes frames before it authenticates; an oversized frame closes the
  connection with 1009.
* A message that fails validation is answered and logged with only its error type, never its input
  or the decoder's text, which can quote the input.

## Persistence and credentials

The lobby reads what the game server writes, and signs what it verifies, so `store`, `replayfile` and
`auth` keep the formats the lobby reads and signs.

* The SQLite file is shared. The game server creates only `played_games` and its index, in the
  lobby's DDL; the lobby creates its own tables when it opens the file. A row is the JSON the lobby's `PlayedGame` validates.
  `testdata/python_rows.json` holds rows Python wrote, and Go must write them byte for byte but for
  `final_score_unit`: every row Go writes ends with that key (`store.FinalScoreUnit`), its final scores
  in tenths. A row without it holds the Python server's whole points until the migration converts it.
* A game's row is its id's durable claim: the start insert keeps an existing row and returns
  `store.ErrGameRecorded`, so once a game's start row is written its id is never played again. A
  game that wrote none (abandoned or withdrawn while pending, refused by the engine, or whose start
  write failed) leaves no claim in the store.
* At startup, once its listener is bound, the server closes every row with no end as `error`, as
  `RecordFailed` would: no game survives a restart, so such a row is a game a crash or a shutdown
  left unfinished. This holds only while exactly one game server writes a database
  (`AUTH_DATABASE_PATH`): a second server on another address would have its live games closed, and
  nothing guards that; the bind only stops a second launch on the same address before the sweep.
* Replay files keep their layout, gzip, owner-only modes and 1 MiB read cap; every path goes
  through an `os.Root`, so no id or link leaves the replay directory.
* A ticket verifies only as the lobby signs one: padded base64url (padding required, the URL
  alphabet), exactly the four fields, `expires_at` a JSON float. `testdata/lobby_tickets.json`
  holds tickets the lobby's code signed and the verdict `verify_game_ticket` reached on each. An empty secret
  verifies nothing.

## Engine purity

The engine is synchronous and deterministic: it does no transport and no I/O, reads no clock, starts
no goroutine and draws randomness only from the seed it is given. The caller holds each `Game`; the
engine keeps no registry and no mutable package-level state. `make lint-go` holds this for non-test
code under `engine/`:

* Imports are an allow-list (`engine-purity`, depguard in strict mode): the engine's own packages and
  a short set of pure standard-library packages. When the engine needs
  another pure package, add it to the list; an allow entry is a prefix, so end it with `$` to keep
  `math` from admitting `math/rand`.
* `time` is allowed for its types only: time crosses the facade as values the caller passes in
  (forbidigo holds the rest).
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
* A switch over a sum type or an enum lists every variant; a `default:` does not cover a missing one. A
  package that switches over a sum type imports the package that declares it, since gochecksumtype does not
  see through a type alias.
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
* `seam/testdata/traces.jsonl.gz` is a fixed set of recorded games (`seam/testdata/README.md`) whose
  actions the replay tests play through the engine. A wanted rule change that stops one of them
  playing through raises a question about that data; it is never a reason to leave the change undone.
* A game's scenario tests play it through `engine/internal/testkit`, which stages walls and scripts
  actions. testkit is engine code: it never imports `testing` and never
  asserts, returning values or errors, and it has its own tests. It imports `game`, so only external
  test packages (`package game_test`) use it. A test compares engine states with go-cmp, every
  field exported (`cmp.Exporter`) and empty slices equal to nil.
* Engine state is a value: a slice in it is replaced, never written in place, so a state a caller
  kept stays as it was. A branch test plays two actions from one state and checks the state and
  both branches against fresh replays; one is written for each kind of change that touches a slice.
* Test names follow `Test<Subject>_When<Condition>_Should<Expected>`; drop `When<Condition>` only for
  unconditional behaviour (`TestNewGame_ShouldYieldStartedEventWithFullWall`).
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

A comment explains business logic, and only where the code really cannot say it.

## Tooling

* Go and golangci-lint are pinned in the repo-root `mise.toml`, and `go.mod`'s `go` line matches the
  pinned Go. The Makefile puts both on `PATH` for its own targets only, so a `go` command typed
  outside `make` goes through `mise exec --`.
* `make format-go` rewrites files. There is no Go typecheck target: `make lint-go` stands in.
  `make test-go`'s race pass leaves out the engine and `seam/`, which start no goroutine and are
  slowest under `-race`; its shuffled pass is never cached, so a test that reads a file outside the
  module (`telegraf.conf`) still runs every time.
* Go has no release-age setting like the 7-day cooldown uv and npm apply here, so it is a convention.
  Add or upgrade a dependency only at an explicit version published at least 7 days ago:
  `mise exec -- go list -m -json <module>@vX.Y.Z` prints its `Time`, then
  `mise exec -- go get <module>@vX.Y.Z`, one module at a time. Never `go get <module>@latest` or
  `go get -u`, which take a version published minutes ago. A security fix younger than 7 days is the
  one exception, and the commit body says so.
* `make vuln-go` runs govulncheck over the module. It needs the network, so it is not part of
  `make run-all-checks`: run it after adding or upgrading a dependency.
* Production runs this server from the release image `deploy/Dockerfile` builds (`deploy/AGENTS.md`);
  its `game` target is the server alone, which `make run-game-v2-docker` starts as the local
  `game-v2` service (`docker-compose.local.yml`). That compose runs it as the host user, because the
  dev database and the replays are owner-only and the host's lobby reads both, and mounts the whole
  `var/` directory, not the database file, so SQLite's WAL and SHM siblings are the ones the host's
  lobby uses. The container holds `:8712`, and `make run-local-server` and `make run-games` cannot
  kill it: stop it first (`make stop-game-v2-docker`) unless they run in their `DOCKER=1` mode.
