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
  that seat is resolved. A provably invalid action (`InvalidGameActionError`) disconnects the
  offending seat with code 1008; an ordinary rule error only answers with an error. When the last human leaves,
  the game is torn down: there are never all-AI games, and no reconnect after that.
* **Reconnect:** the router verifies the ticket; the session must be disconnected and belong to the
  path's game. Under the lock: evict stale connections, remove the AI player
  (`restore_human_player`), send the `game_reconnected` snapshot, broadcast `player_reconnected`, and
  re-send the draw if it is that player's turn (directly, so the replay collector does not record it
  twice). Close evicted connections outside the lock.
* **Game end.** A finished game is marked `ended` before its replay save and finish record; the
  sockets close after them. An action, a timeout or a reconnect that reaches an ended game is
  refused (reconnect with `reconnect_game_gone`, before any eviction or seat restore).
* **Server failure.** `fail_game(game, reason, exc)` is the one terminal path for a server fault.
  It is synchronous and lock-agnostic: before anything can suspend it marks the game ended and drops
  it from the registry with its pending entry, sleeping timers, lock, engine state and sessions, so
  no other path can finalize it, then hands the effects to a finalizer task it owns: record
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
