# Game sessions

`SessionManager` owns game and player lifecycle, delegating to `SessionStore` (in-memory sessions),
`TimerManager`, `HeartbeatMonitor` and `ReplayCollector`. Work that touches a game runs under its
per-game lock.

* **Pending game.** `POST /games` registers a session per player, keyed by the player's game ticket
  string — the ticket is the session token for the whole game, never rotated. The game waits for
  `4 - num_ai_players` humans to send `JOIN_GAME`; it starts when they all have, or when the pending
  timeout (10s) fires, with AI players in the empty seats. With no humans it is cancelled.
* **Disconnect** from a started game: an AI player takes the seat, the player's timer stops and the
  remaining bank time is saved on the session, and any pending turn, call or round confirmation for
  that seat is resolved. An invalid action disconnects with code 1008. When the last human leaves,
  the game is torn down: there are never all-AI games, and no reconnect after that.
* **Reconnect:** the router verifies the ticket; the session must be disconnected and belong to the
  path's game. Under the lock: evict stale connections, remove the AI player
  (`restore_human_player`), send the `game_reconnected` snapshot, broadcast `player_reconnected`, and
  re-send the draw if it is that player's turn (directly, so the replay collector does not record it
  twice). Close evicted connections outside the lock.
* **Timers** (`TurnTimer`, one per player): each turn gets base time (5s), then a bank (20s start,
  +10s per round, 60s cap) that drains only past the base time. Meld-call and round-advance timers
  are fixed and never touch the bank.
* **Replays:** `ReplayCollector` keeps broadcast events plus each seat's draws (without available
  actions), merges the per-seat `round_started` views into one record holding every hand, adds the
  seed to `game_started`, and saves gzip NDJSON with a version line on game end.
* **Persistence** of game starts and ends (`GameRepository`) is best-effort: log a database failure,
  never let it block gameplay or socket cleanup.
