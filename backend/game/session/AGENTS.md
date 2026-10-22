# Game sessions

`SessionManager` is the registry of live games and connections and runs each game's lifecycle
transitions. A game is a `GameSession` (`models.py`): its participants, pacing (`TimerConfig`),
lifecycle, last engine wait, start record, replay lines, pending timeout and one lock for its whole
life. Work that touches a game runs under that lock, and under it only enqueues to sockets: a send
or close never waits on a client. Nothing under the lock suspends any more; C16 deletes it with the
re-checks that follow its acquisition (connection identity, lifecycle, timer arm generations).

* **Registry.** It holds only pending and playing games (by id), their participants (by game
  ticket), the registered connections and which participant each authenticated connection is bound
  to. A stale reference checks `game.lifecycle`, never the registry by id, so a game id is reusable
  the moment its end is claimed.
* **Lifecycle** (`GameLifecycle`): PENDING → PLAYING → ENDING → CLOSED, or PENDING → ENDING. PLAYING
  is set synchronously at the start, ENDING by the one end claim, CLOSED by the finalizer when the
  end's effects are done. Requests dispatch on it: JOIN_GAME is for a pending game (a playing one
  answers `join_game_already_started`); RECONNECT to a pending game answers `reconnect_retry_later`;
  a game action to a pending game answers `game_not_started`; anything reaching an ended game is
  dropped or refused.
* **Participants.** `POST /games` creates one `Participant` per `PlayerSpec`, keyed by its game
  ticket, which is the participant's token for the whole game, never rotated. A participant is
  connected while it has a connection; its seat is bound once, at the start, to the seat
  `start_game` returned for its spec (by input order, never by name); its `TurnTimer` lives as long
  as it does. Every engine call names the player by seat.
* **Pending game.** It waits for every participant's `JOIN_GAME`; it starts when they are all
  connected, or when the pending timeout fires with at least one connected, with AI players in the
  absent seats (an absent participant can RECONNECT later). With nobody connected the timeout
  abandons it. A JOIN_GAME for a participant that already has a connection moves it to the new one
  and evicts and closes the old one. A participant who drops before the start just waits for a new
  JOIN_GAME.
* **Disconnect** from a playing game: an AI player takes the seat and plays any turn, call or round
  confirmation it owed, and the participant's timer stops, deducting the bank it used.
  Structurally impossible input (`InvalidGameActionError`, always the acting human's own seat)
  does the same and closes that connection with 1008; a rule judgment or race only answers with an
  `ErrorEvent`; an error while replacing the kicked player is a server fault. A timeout or AI action
  is never a kick. When no connected participant remains the game is abandoned: there are never
  all-AI games.
* **Reconnect:** the router verifies the ticket; the participant must belong to the path's game,
  which must be playing, and must be disconnected (a participant whose old connection the server has
  not seen drop yet answers `reconnect_retry_later`). Under the lock: remove the AI player
  (`restore_human_player`), send the `game_reconnected` snapshot with the current wait id, broadcast
  `player_reconnected`, and, when the engine's current wait (`get_awaiting`) is that seat's turn,
  re-send the draw (directly, so the replay does not record it twice) and start its turn timer.
* **Eviction.** `_evict_connection` drops a connection from the registry and from its participant
  and cancels its auth timeout. Every server-initiated close evicts first (auth timeout, kick, the
  JOIN_GAME duplicate, the game end, a connection a failure did not seat), so a message the client
  pipelined on the closing socket finds it unregistered; a game message on an evicted socket gets no
  answer, since a `not_in_game` ahead of the close would read as a permanent error to the client.
* **The end.** `_end_game(game, reason)` is the one claim, for every reason: COMPLETED (the engine
  reports the game waits for nothing, right after that batch's sends), ERROR (`fail_game`), ABANDONED
  (nobody connected remains, or the pending timeout found nobody). It is synchronous and idempotent:
  only a pending or playing game can be claimed. The claim detaches the connected participants'
  connections and the replay lines (an abandoned game's are discarded) and spawns one finalizer
  task the manager owns on them, then releases the game from the registry with its tickets, cancels
  the pending timeout and every sleeping timer, evicts those connections and frees the engine state.
  The finalizer saves the replay, posts the finish record and closes the connections (1000
  `game_ended` for a completion; for a failure the `internal_error` session error, then 1011). Each
  step and each close is its own error boundary; an unexpected error saving a completed game's
  replay turns its end into a failure. The game end is queued to every socket before the finalizer
  queues its close.
* **Server failure.** `fail_game(game, reason, exc)` is the one terminal path for a server fault:
  callable from any context, before the start included, it claims the end as ERROR and never
  cancels or awaits the current task; a caller that gets it back skips its own broadcast and timers.
* **Playing.** A user plays a game while one of their participants is in a registered game: from
  `POST /games` (pending included) until its end is claimed. A disconnected participant still
  counts, deliberately: the lobby keeps that user out of rooms and matchmaking until the game ends.
  The internal per-user lookup the lobby asks and the 409 `POST /games` gives a user already playing
  both answer from this rule.
* **Background tasks.** Pending and auth timeouts and end finalizers are spawned through `_spawn`
  and stay owned until done; `TimerManager` tracks running timer callbacks; a fired `TurnTimer`
  detaches its task before its callback, so a stop, cancel or restart from inside the callback
  leaves it running and keeps the timer it arms. Every start, stop and cancel bumps the timer's arm
  generation: a fired callback that finds it changed once it holds the game lock, or whose
  participant is no longer connected, does nothing. `shutdown` cancels the sleeping tasks and awaits
  the rest. Timer callbacks and the pending timeout fail their game on an unexpected error.
* **Timers** (`TurnTimer`, one per participant): each turn gets base time (5s), then a bank (20s
  start, +10s per round, 60s cap) that drains only past the base time; the browser client's silence
  watchdog limit is derived from these defaults (`frontend/AGENTS.md`). Meld-call and round-advance
  timers are fixed and never touch the bank. The engine's `Awaiting` drives them, never the events
  (`_follow_engine`, `GameSession.awaiting` holds the last one): when an action, timeout,
  replacement or the game start brings a new wait id, the actor's timer stops (deducting its bank on
  a turn) and the others are cancelled before the events go out, then the new wait's connected seats
  get their turn, meld or round-advance timers; the first wait of a round adds the round bonus to
  every connected participant's bank, the game start's included. With the wait id unchanged only an
  actor that left the wait (a partial pass or confirmation) has its timer stopped, and a refused
  action leaves the running deadline alone. Every game pacing duration comes from the manager's
  `TimerConfig`, the session's one pacing model; the engine has none. Connection-level timing (the
  auth timeout, the transport ping) is not pacing.
* **Stale actions.** Every game action echoes the wait id (`wi`) the server stamped on the message
  that opened the wait. Under the lock, an action whose id is not `GameSession.awaiting.wait_id`
  gets a `stale_action` ErrorEvent to its seat and touches neither the engine nor a timer.
* **Replays:** each game holds its `ReplayRecord` from the start until the end claim detaches it.
  `ReplayCollector` shapes the lines (broadcast events plus each seat's draws without available
  actions, the per-seat `round_started` views merged into one record holding every hand, the seed
  on `game_started`) and saves gzip NDJSON with a version line.
* **Persistence** of game starts and ends (`GameRepository`, required) is best-effort and never
  awaited: the session posts each record and goes on, and the repository logs a failed write. The
  start record (`GameSession.start_record`) is captured right after `start_game`, every seat in
  seat order, each participant's `user_id` by seat (so AI seats get none even when a human shares an
  AI-style name). Every finish record, completed, abandoned or failed, is built whole from it
  (`build_finish_record`) plus, for a completion, the `GameEndedEvent` standings in placement order;
  never from engine or connection state at the end, so a never-connected or departed seat keeps its
  name and `user_id`. A game with no start record (it never started) records no finish. The finish
  is an upsert: it lands even when the start write failed, and the first finish wins.
