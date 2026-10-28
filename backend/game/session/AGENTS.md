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
* **One connection per participant; the newest wins.** A JOIN_GAME or RECONNECT for a participant
  still bound to a connection (a half-open socket the server has not seen drop, or another tab)
  replaces it through the one binder (`_bind`): the old connection is evicted, then closed with
  4002 `replaced_by_new_connection`, which the client treats as terminal so two live clients cannot
  take the seat back from each other forever. A connection already bound is refused before anyone
  is replaced. A replacement is not a disconnect: no `player_left` or `player_reconnected`, no AI
  player, no engine call, and the wait, its timers and the bank carry on, so the old connection's
  late input and disconnect resolve to no participant (`_bound`) and touch nothing. The reconnect
  snapshot says during a round advance whether the seat still owes its confirmation, which only a
  replacement can make true: a disconnect confirms the seat, and a seat an AI player held at the
  round end was never required.
* **Playing.** A user plays a game from its creation (pending included) until its end is claimed,
  and a disconnected participant still counts, deliberately: the lobby keeps that user out of rooms
  and matchmaking until the game ends. The lobby's per-user lookup, its recovery of the participant's
  own ticket for a lost handoff, and `POST /games`' refusal of a user already playing all answer from
  this rule.
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
  needs a longer limit. The client also re-implements the turn, call, bank, round advance and game
  start pause rules from the timer settings it is sent once, taking only the bank from each turn's
  opening message (`messaging/AGENTS.md`), so a change to how a wait is paced changes its countdown
  too. A new round's bonus goes into the banks before the wait's events go out, so that bank
  includes it.
* **Finish records come from the start record.** The start record is captured right after the
  engine starts the game, every seat in seat order with each participant's `user_id` by seat; every
  finish record (completed, abandoned or failed) is built whole from it, never from engine or
  connection state at the end, so a never-connected or departed seat keeps its name and `user_id`
  and AI seats never get one. A game that never started records no finish; the finish is an upsert
  that lands even when the start write failed, and the first finish wins.
* **Replays.** A game's replay lines are collected from the start and detached by the end claim; an
  abandoned game's are discarded, and a failure to save a completed game's replay turns its end
  into a failure. A reconnect re-sends the opening event of the wait the game owes the seat (its
  draw, its `turn` event or its call prompt) directly, outside the replay path, so it is not
  recorded twice, and re-arms no timer: only a replaced connection's seat can be awaited, and its
  timer kept running, so the event carries how long it has run for the client's countdown.
  Beside the events the session writes replay-only annotation lines, the seat control lines, which
  follow who plays each seat:
  * an AI replacement goes in ahead of the AI player's moves, with its reason: `left` for a
    disconnect (a kick included), which may fall between rounds, during a round advance;
  * a seat with no connection at the first deal, never joined or gone during the game start pause,
    is recorded `absent` after the deal's events (the start pause hands no seat over, so nothing is
    written before the first round), and the replay viewer counts it an AI player's from the deal;
  * a reconnect that takes the seat back from its AI player writes a human return;
  * a connection replacement writes nothing: its seat never left its human.

  The replay runner skips them; they only tell a viewer what happened.
* **Each task logs as its own subject.** A task copies the structlog context of whatever spawned
  it, often another seat's action, so a fired timer binds its game and its own seat, and the
  finalizer its game with no seat; a new background task rebinds its context the same way.
* **A graceful stop is a disconnect.** The manager has no drain of its own: a graceful stop ends
  games only through the normal leave of each closed socket, and `shutdown()` ends no game. A
  separate shutdown classification would need a drain signal ahead of the socket closes, which
  uvicorn does not give. The sequence is in `docs/architecture.md`.
