# Game sessions

`SessionManager` owns game and player lifecycle, delegating to `SessionStore` (in-memory sessions),
`TimerManager`, `HeartbeatMonitor` and `ReplayCollector`. Work that touches a game runs under its
per-game lock.

* **Pending game.** `POST /games` registers a session per player, keyed by the player's game ticket
  string — the ticket is the session token for the whole game, never rotated. The game waits for
  `4 - num_ai_players` humans to send `JOIN_GAME`; it starts when they all have, or when the pending
  timeout (10s) fires, with AI players in the empty seats. With no humans it is cancelled. At
  start every expected human's session is bound to its seat before AI players fill the absent
  ones, and an absent human's session is marked disconnected, so it can RECONNECT later.
* **Disconnect** from a started game: an AI player takes the seat, the player's timer stops and the
  remaining bank time is saved on the session, and any pending turn, call or round confirmation for
  that seat is resolved. Structurally impossible input (`InvalidGameActionError`, always the acting
  human's own seat) disconnects that player with code 1008 and seats an AI player; a rule judgment or
  race only answers with an `ErrorEvent`; an error while replacing the kicked player is a server
  fault (`fail_game`). A timeout or AI action is never a kick. When the last human leaves,
  the game is torn down: there are never all-AI games, and no reconnect after that.
* **Reconnect:** the router verifies the ticket; the session must be disconnected and belong to the
  path's game. Under the lock: evict stale connections, remove the AI player
  (`restore_human_player`), send the `game_reconnected` snapshot, broadcast `player_reconnected`, and
  re-send the draw if it is that player's turn (directly, so the replay collector does not record it
  twice). Close evicted connections outside the lock.
* **Game end.** Exactly one path finalizes a game, and it claims `Game.end_reason` synchronously
  before its first await: a completion claims it as soon as the engine's events end the game,
  before the game-end broadcast, unless `fail_game` claimed it first; `fail_game` claims it the same
  way. The claimer is bound to finish: right after its game-end broadcast the same path saves the
  detached replay, records the finish and closes the sockets. If the broadcast or the replay save
  raises, it escalates its own claim to a failure, finished by the fail_game finalizer; once the
  finish record is written (best-effort, as all persistence) the completion stands, and a socket
  whose close fails is logged while the rest still close. Only the claimer escalates; a concurrent
  `fail_game` still finds the game ended and does nothing. An action, a timeout or a reconnect that reaches an ended game is refused
  (reconnect with `reconnect_game_gone`, before any eviction or seat restore).
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
  are fixed and never touch the bank.
* **Replays:** `ReplayCollector` keeps broadcast events plus each seat's draws (without available
  actions), merges the per-seat `round_started` views into one record holding every hand, adds the
  seed to `game_started`, and saves gzip NDJSON with a version line on game end.
* **Persistence** of game starts and ends (`GameRepository`) is best-effort: log a database failure,
  never let it block gameplay or socket cleanup.
