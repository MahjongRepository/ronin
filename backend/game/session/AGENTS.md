# Game sessions

`SessionManager` owns game and player lifecycle, delegating to `SessionStore` (in-memory sessions),
`TimerManager`, `HeartbeatMonitor` and `ReplayCollector`. Work that touches a game runs under its
per-game lock, and under it only enqueues to sockets: a send or close never waits on a client.

* **Pending game.** `POST /games` registers a session per player, keyed by the player's game ticket
  string — the ticket is the session token for the whole game, never rotated. The game waits for
  every player in the request to send `JOIN_GAME`; it starts when they all have, or when the pending
  timeout (10s) fires, with AI players in the empty seats. With no humans it is cancelled. At
  start every expected human's session is bound to the seat `start_game` returned for its spec (by
  input order, never by name), and an absent human's session is marked disconnected and its seat
  given to an AI player, so it can RECONNECT later. Every engine call names the player by seat.
* **Disconnect** from a started game: an AI player takes the seat, the player's timer stops and the
  remaining bank time is saved on the session, and any pending turn, call or round confirmation for
  that seat is resolved. Structurally impossible input (`InvalidGameActionError`, always the acting
  human's own seat) disconnects that player with code 1008 and seats an AI player; a rule judgment or
  race only answers with an `ErrorEvent`; an error while replacing the kicked player is a server
  fault (`fail_game`). A timeout or AI action is never a kick. When the last human leaves,
  the game is torn down: there are never all-AI games, and no reconnect after that.
* **Reconnect:** the router verifies the ticket; the session must be disconnected and belong to the
  path's game. Under the lock: evict stale connections, remove the AI player
  (`restore_human_player`), send the `game_reconnected` snapshot with the current wait id, broadcast
  `player_reconnected`, and, when the engine's current wait (`get_awaiting`) is that seat's turn,
  re-send the draw (directly, so the replay collector does not record it twice) and start its turn
  timer. Close evicted connections outside the lock.
* **Game end.** Exactly one path finalizes a game, and it claims `Game.end_reason` synchronously
  before its first await: a completion claims it as soon as the engine reports the game waits for
  nothing (`Awaiting.kind` NONE), before the game-end broadcast, unless `fail_game` claimed it
  first; `fail_game` claims it the same way. The claimer is bound to finish: right after its
  game-end broadcast the same path saves the detached replay, records the finish and closes the
  sockets. If the broadcast or the replay save raises, it escalates its own claim to a failure,
  finished by the fail_game finalizer; once the finish record is posted (best-effort, as all
  persistence) the completion stands. Only the claimer escalates; a concurrent `fail_game` still
  finds the game ended and does nothing. An action, a timeout or a reconnect that reaches an ended
  game is refused (reconnect with `reconnect_game_gone`, before any eviction or seat restore).
* **Playing.** A user plays a game while they have a session in a registered game that has not
  ended: from `POST /games` (pending included) until the game's end is claimed or it is torn down.
  A disconnected session still counts, deliberately: the lobby keeps that user out of rooms and
  matchmaking until the game ends. The internal per-user
  lookup the lobby asks and the 409 `POST /games` gives a user already playing both answer from
  this rule.
* **Game ids are reusable** once a game leaves the registry. Teardown releases everything keyed by
  the id before its first await, delayed effects use only objects detached synchronously, and a
  player's game is resolved by membership (`_game_of`), never by id alone.
* **Server failure.** `fail_game(game, reason, exc)` is the one terminal path for a server fault,
  and a completion that fails while finishing escalates into the same finalizer.
  It is synchronous and lock-agnostic: before anything can suspend it claims the game's end, drops
  it from the registry with its pending entry, sleeping timers, lock, engine state and sessions, and
  detaches its heartbeat loop and replay lines, then hands those to a finalizer task it owns: record
  `end_reason="error"`, save whatever replay history exists (unchanged format), send every connected
  player an `internal_error` session error, close with 1011; a failing step is logged and the rest
  still run. It is idempotent, works before start, and never cancels or awaits the current task; a
  caller that gets it back skips its own broadcast and timers.
* **Background tasks.** Pending and auth timeouts and fail_game finalizers are spawned through
  `_spawn` and stay owned until done; `TimerManager` tracks running timer callbacks; a fired
  `TurnTimer` detaches its task before its callback, so a stop, cancel or restart of that seat from
  inside the callback leaves it running and keeps the timer it arms. Every start, stop and cancel
  bumps the timer's arm generation: a fired callback that finds it changed once it holds the game
  lock (the player acted, the prompt resolved, the seat was replaced) does nothing. `shutdown`
  cancels the sleeping tasks and awaits the rest. Timer and heartbeat callbacks and the pending
  timeout fail their game on an unexpected error.
* **Timers** (`TurnTimer`, one per player): each turn gets base time (5s), then a bank (20s start,
  +10s per round, 60s cap) that drains only past the base time. Meld-call and round-advance timers
  are fixed and never touch the bank. The engine's `Awaiting` drives them, never the events
  (`_follow_engine`, `Game.awaiting` holds the last one): when an action, timeout, replacement or
  the game start brings a new wait id, the actor's timer stops (deducting its bank on a turn) and
  the others are cancelled before the events go out, then the new wait's connected seats get their
  turn, meld or round-advance timers; the first wait of a round adds the round bonus to every bank,
  the game start's included; a game over cancels them all. With the wait id unchanged only an actor
  that left the wait (a partial pass or confirmation) has its timer stopped, and a refused action
  leaves the running deadline alone. Every game pacing duration (turn, bank, meld, round advance,
  pending timeout) comes from the game's `TimerConfig` (`Game.timer_config`), the session's one
  pacing model; the engine has none. Connection-level timing (auth timeout, heartbeat) is not
  pacing.
* **Stale actions.** Every game action echoes the wait id (`wi`) the server stamped on the message
  that opened the wait. Under the lock, after the ended check, an action whose id is not
  `Game.awaiting.wait_id` gets a `stale_action` ErrorEvent to its seat and touches neither the
  engine nor a timer.
* **Replays:** `ReplayCollector` keeps broadcast events plus each seat's draws (without available
  actions), merges the per-seat `round_started` views into one record holding every hand, adds the
  seed to `game_started`, and saves gzip NDJSON with a version line on game end.
* **Persistence** of game starts and ends (`GameRepository`, required) is best-effort and never
  awaited: the session posts each record and goes on, so recording adds no suspension point, and
  the repository logs a failed write. The start record (`Game.start_record`) is captured right after
  `start_game`, every seat in seat order, each human's `user_id` by seat (so AI seats get none even
  when a human shares an AI-style name). Every finish record, completed, abandoned or failed, is
  built whole from it (`build_finish_record`) plus, for a completion, the `GameEndedEvent`
  standings in placement order; never from engine or connection state at the end, so a
  never-connected or departed seat keeps its name and `user_id`. A game with no start record (it
  never started) records no finish. The finish is an upsert: it lands even when the start write
  failed, and the first finish wins.
