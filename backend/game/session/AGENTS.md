# Game sessions

`SessionManager` (`manager.py`) is the registry of live games and connections and runs each game's
lifecycle transitions: pending games, joins, disconnects, reconnects, timeouts, the start and the
one end. `models.py` holds `GameSession` and its `Participant`s, `timer.py` the pacing
(`TimerConfig`, `TurnTimer`), `replay_collector.py` the shaping and saving of replay lines,
`played_game.py` the finish record.

## Design

A transition (a join, an action, a disconnect, a reconnect, a timeout, the start, the end claim) is
one synchronous step, and so is `MessageRouter`'s dispatch to it: none can suspend, none interleave,
and none needs a lock. Sends and closes only enqueue, so a step never waits on a client; the only
awaits are the timers' sleeps, the end finalizer and shutdown. The guards that remain sit at real
I/O completions: a client message checks that its connection is still registered or bound, and an
action checks its wait id. Keep new transitions synchronous: an `await` inside one lets steps
interleave.

## Invariants

* **One end claim.** Every game ends through the same claim, for every reason (completed, server
  error, abandoned); it is synchronous and idempotent, releases the game and its tickets from the
  registry at once, and hands the effects (replay save, finish record, closes) to one finalizer task
  the manager owns. A stale reference checks the game's lifecycle, never the registry, so a game id
  is reusable the moment its end is claimed.
* **One server-fault path.** `fail_game` is the only way a server fault ends a game: callable from
  any context, before the start included, it claims the end as an error and never cancels or awaits
  the current task. A caller that gets it back skips its own broadcast and timers.
* **Participants.** One per `PlayerSpec`, keyed by its game ticket for the whole game, never
  rotated; its seat is bound once, at the start, to the seat the engine returned for its spec (by
  input order, never by name), and its timer lives as long as it does, so its bank survives a
  disconnect. A disconnected seat is played by an AI player until the participant reconnects; when
  no connected participant remains the game is abandoned, so there are never all-AI games.
* **Playing.** A user plays a game from its creation (pending included) until its end is claimed,
  and a disconnected participant still counts, deliberately: the lobby keeps that user out of rooms
  and matchmaking until the game ends. The lobby's per-user lookup and `POST /games`' refusal of a
  user already playing both answer from this rule.
* **Evicted sockets stay silent.** A connection the server closes leaves the registry in the same
  step, and a message that then arrives on it gets no answer: its close is queued or follows from
  the finalizer, and an error ahead of it would read as a permanent error to the client.
* **Stale actions.** Every game action echoes the wait id the server stamped on the message that
  opened the wait; an action for any other wait gets a stale-action `ErrorEvent` and touches
  neither the engine nor a timer.
* **Timers need no generation or lifecycle check.** Every path that supersedes a wait (ending it,
  releasing a seat, leaving PENDING, authenticating or evicting a connection, ending the game)
  cancels the timers it supersedes, so a timer that runs at all runs on the state it was armed for.
* **Pacing.** The engine's `Awaiting` drives the timers, never the events: a new wait id re-arms
  them for the new wait's connected seats, an unchanged one touches only an actor that left it.
  Every pacing duration comes from `TimerConfig`, the one pacing model (the engine has none; the
  auth timeout and transport ping are not pacing). A round advance waits its timeout once per result
  the client shows in turn, so a double ron's waits it once per winner. The game start pause holds
  the first deal back after `game_started` so the client shows the start: no wait is open and no
  timer runs until the deal, a seat left empty then gets its AI player only with the deal (no AI
  move goes out ahead of it), and a RECONNECT answers retry later until then. The game client's
  silence watchdog limit is derived from its defaults (`frontend/game/AGENTS.md`), so a longer wait
  needs a longer limit. The client also re-implements the turn, call and bank rules from the timer
  settings it is sent once (`messaging/AGENTS.md`), so a change to how a wait is paced changes its
  turn clock too.
* **Finish records come from the start record.** The start record is captured right after the
  engine starts the game, every seat in seat order with each participant's `user_id` by seat; every
  finish record (completed, abandoned or failed) is built whole from it, never from engine or
  connection state at the end, so a never-connected or departed seat keeps its name and `user_id`
  and AI seats never get one. A game that never started records no finish; the finish is an upsert
  that lands even when the start write failed, and the first finish wins.
* **Replays.** A game's replay lines are collected from the start and detached by the end claim; an
  abandoned game's are discarded, and a failure to save a completed game's replay turns its end
  into a failure. A reconnect re-sends the turn's opening event (its draw or `turn` event)
  directly, outside the replay path, so a draw is not recorded twice.
