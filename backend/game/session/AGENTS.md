# Game sessions

`SessionManager` (`manager.py`) is the registry of live games and connections and runs each game's
lifecycle transitions: pending games, joins, disconnects, reconnects, timeouts, the start and the
one end. `models.py` holds `GameSession` and its `Participant`s, `timer.py` the pacing
(`TimerConfig`, `TurnTimer`), `replay_collector.py` the shaping and saving of replay records,
`played_game.py` the finish record, `seating.py` each game's seed and seating, `ai_player.py` the AI players' choice.

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
  rotated; its seat is bound once, at the start, to the seat the session's seating gives its spec (by
  input order, never by name), and its timer lives as long as it does, so its bank survives a
  disconnect. A disconnected seat is played by an AI player until the participant reconnects; when
  no connected participant remains the game is abandoned, so there are never all-AI games. Every
  handover, either way, goes through one step (`_hand_over_seat`): the replay records its seat
  control record and the connected participants get `seat_control`, both ahead of the moves that
  follow, and the participant keeps why it stands in, which the reconnect snapshot carries.
* **The session owns the roster and the seed.** It draws each game's seed from its seed source and
  seats the participants by the seed's seat permutation (`seating.py`, `docs/rng.md`), the rest
  AI players named apart from them; the engine gets only the seed. The game id, every seat's name and
  the AI seats form the game's roster, which messaging adds to `game_started` and the reconnect
  snapshot. The start record and the replay's seats come from the roster, the replay's seed from the
  seed source and its RNG version from the `RNG_VERSION` constant, never from engine state.
* **The session plays the AI players.** The engine names every awaited seat and never learns who
  answers one: a seat no participant takes, or one whose participant has no connection, is an AI
  player's (`GameSession.is_ai_seat`), and the session answers it through `act` like a participant's
  answer, from the seat's decision read at that moment (`ai_player.py`: the decision's default, a
  pass on every call and the default discard on its turn, so it never wins, calls or declares riichi,
  a kan or kyuushu). After each engine call, every call an AI player's seat is awaited on is answered
  at once, in ascending seat order, one `act` each whose events go out before the next; an AI
  player's turn waits the AI turn delay (below). Each answer is an engine call whose actor is that AI
  player's seat, and its seat gets no timer, no decision id and no opening, since it has no connected
  participant. A refused AI player's answer is a server fault. The engine checks furiten once per
  call, so with each AI answer its own call, a seat's furiten change can arrive ahead of the draw
  that follows an AI-only call window.
* **The session opens each decision.** The engine emits facts and keeps no prompt: after every
  engine call that opens a new wait, the session reads the `decision` of each newly awaited
  connected participant's seat and has messaging build its opening (`messaging/AGENTS.md`), placed
  among that call's events so each seat gets its messages in the engine's order, then stamps it with
  the seat's decision id and bank. A kept wait (a partial call answer) sends no opening and re-times
  nothing. A reconnect or resync reads the seat's `view` once and builds both its snapshot and the
  opening of the view's decision from it and the session's own data, with no other engine read.
* **One connection per participant; the newest wins.** A JOIN_GAME or RECONNECT for a participant
  still bound to a connection (a half-open socket the server has not seen drop, or another tab)
  replaces it through the one binder (`_bind`): the old connection is evicted, then closed with
  4002 `replaced_by_new_connection`, which the client treats as terminal so two live clients cannot
  take the seat back from each other forever. A connection already bound is refused before anyone
  is replaced. A replacement is not a disconnect: no `seat_control`, no AI
  player, no engine call, and the wait, its timers and the bank carry on, so the old connection's
  late input and disconnect resolve to no participant (`_bound`) and touch nothing. The reconnect
  snapshot says during a pause whether the seat still owes its confirmation, which only a
  replacement can make true: a disconnect takes the seat out of the pause, and a seat an AI player held when the
  pause opened never owed it.
* **A resync is a reconnect without the socket.** A RESYNC on the connection that holds a seat gets
  exactly what a reconnect sends it (the snapshot, then the wait the game owes the seat with how long
  its timer has run), through the same step, on that connection, and is read-only: nothing is
  rebound, handed over, stored, recorded or re-armed, and no other seat hears of it, so a client that lost step recovers without its
  seat passing to an AI. A pending game refuses it as not started; from the start on it is answered, the game
  start's confirmation included.
* **Playing.** A user plays a game from its creation (pending included) until its end is claimed,
  and a disconnected participant still counts, deliberately: the lobby keeps that user out of rooms
  and matchmaking until the game ends. The lobby's per-user lookup, its recovery of the participant's
  own ticket for a lost handoff, and `POST /games`' refusal of a user already playing all answer from
  this rule. A pending game nobody joined ends early when the lobby withdraws it; a withdrawn id is
  refused for a ticket's lifetime, so a creation that arrives after its withdrawal never registers.
* **Evicted sockets stay silent.** A connection the server closes leaves the registry in the same
  step, and a message that then arrives on it gets no answer: its close is queued or follows from
  the finalizer, and an error ahead of it would read as a permanent error to the client.
* **Stale actions.** Every game action echoes the wait id the server stamped on the message that
  opened that participant's decision. `Participant.decision_id` increases only when a new
  wait, or the pause opening with it, opens a decision for that connected participant; it survives replacements and reconnects,
  and never advances for other seats or for an absent participant's AI stand-in. The engine knows no wait or decision
  identity: the session tells a new wait from a kept one by comparing what each engine call reports it awaits with the
  wait before (`_opens_new_wait`). A call's actor (the seat that acted, an AI player's included, or timed out) no
  longer holds its decision, so the wait is kept only while its kind is unchanged and it awaits only seats that held
  their decision before the call: a partial call answer keeps the other callers' decisions and timers, while a kan's
  replacement draw for the same seat opens a new one. A human taking back the AI player's turn of its seat opens a new
  one too, with no engine call (`_take_back_decision`). A seat not awaited, or an id different from that
  participant's latest, gets the same stale-action `ErrorEvent` and touches neither the engine nor
  a timer, so guessed ids reveal no hidden waits. A call answer whose called tile is not the open call's is refused
  by the session too, with that answer's invalid code, and never reaches the engine. Every `ErrorEvent` answering an
  action names the wait id the action echoed (`messaging/AGENTS.md`, Wait identity).
* **Refusals are the session's policy.** The engine returns a refused action's `Refusal` and changes nothing; the
  session decides what follows. A rule judgment or an action the engine does not await now gets an `ErrorEvent` to the
  seat (messaging maps the refusal to the wire code and message), and the decision, its id and its timer go on;
  structurally impossible input (not offered, a tile not held included) disconnects that human with 1008 and seats an
  AI player. A refused phase call, or a refused timeout default, is a server fault.
* **Timers need no generation or lifecycle check.** Every path that supersedes a wait (ending it,
  releasing a seat, leaving PENDING, authenticating or evicting a connection, ending the game)
  cancels the timers it supersedes, the delayed AI turn included, so a timer that runs at all runs
  on the state it was armed for.
* **Pacing.** The engine's `Awaiting` drives the timers, never the events: a new wait re-arms
  them for its connected seats, a kept one touches only the actor that left it. A turn or call timeout plays the seat's
  `default_action` through `act`, like an answer of the seat's own.
  Every pacing duration comes from `TimerConfig`, the one pacing model (the engine has none; the
  auth timeout and transport ping are not pacing). Both pauses are the session's (`GameSession.pause`): the engine
  stops after a deal and after a round end that does not end the game, awaiting no seat, and the session lets the game
  go on (`deal_next_round` after a round end, then `begin_round` for the dealer's first draw) once every seat that owes
  its confirmation (its connected participants when the pause opened) confirmed with CONFIRM_ROUND, checked against
  its decision id, had its fixed timer confirm for it, or left. A pause opens on the engine's new wait, with a
  decision id for each seat that owes it, and opens no engine decision, so any other action in it is stale. A round
  end's pause waits its timeout once per result the client shows in turn, so a double ron's waits it once per winner,
  counted from the round end. The game start is a pause too, so the client shows the start over the dealt table until
  its players are ready: `game_started` and the deal go out at once, each owing seat's deal stamped as the opening of
  its confirmation, and the dealer draws once every owing seat confirmed or `TimerConfig.game_start_confirm_seconds`
  (a fixed timer, not the round advance's) confirmed for the rest; zero skips it and the dealer draws at once. A seat
  with no connection at the start owes none and gets its AI player right after the deal, and a seat that leaves during
  a pause no longer owes its confirmation, so nobody is held to the timeout by an empty seat. Every AI
  player's turn action waits
  `TimerConfig.ai_turn_delay_seconds` after the move before it, so a human sees AI turns one at a time:
  the turn arms no timer, and one task per game (`GameSession.ai_turn`) plays it after the delay
  through `act` like any other move, which then schedules the next; a zero delay plays them in the
  same step. AI answers to call prompts never wait.
  A new wait or an end claim cancels the delayed AI turn, and a reconnect that takes back a seat whose
  AI turn is still delayed gets that turn as its own new wait, its timer starting with the reconnect.
  The game client derives its silence watchdog limit from the timer settings it is sent and,
  before the game starts, from the pending game timeout `game_joined` names.
  The client also re-implements the shared turn/call bank rules
  from the timer settings it is sent once, taking only the bank from each decision's
  opening message (`messaging/AGENTS.md`), so a change to how a wait is paced changes its countdown
  too; a pause's timeout, the game start's included, is named on the message that opens it and in the
  snapshot instead (`TimerConfig.round_advance_seconds`, which the timer arms too). Every participant's bank resets at each hand's first wait, before its opening messages go out,
  including the first hand and disconnected seats: the session resets them on the wait of each deal. Turns and calls draw from the same bank after their free base
  time; ending a wait charges every running decision, even a call resolved by another seat.
  The timers sleep on the event loop and measure the bank and elapsed time on the manager's clock,
  which every monotonic time the manager reads comes from (`time.monotonic` unless given), so the two
  must agree: the seat scenario generator runs the loop on virtual time and passes the loop's own
  clock, and the session tests pass a fake one.
* **Finish records come from the start record.** The start record is captured right after the
  engine starts the game, every seat in seat order with each participant's `user_id` by seat; every
  finish record (completed, abandoned or failed) is built whole from it, never from engine or
  connection state at the end, so a never-connected or departed seat keeps its name and `user_id`
  and AI seats never get one. A game that never started records no finish; the finish is an upsert
  that lands even when the start write failed, and the first finish wins.
* **Replays.** A game's replay records are collected from the start and detached by the end claim; an
  abandoned game's are discarded, and a failure to save a completed game's replay turns its end
  into a failure. Openings never reach the replay: it records the engine's events only, each draw
  once and none of its notices. A reconnect re-sends the opening of the decision the game owes the
  seat (its draw, its `turn` or its call prompt) directly, outside the replay path, and re-arms no
  timer: only a replaced connection's seat, whose timer kept running,
  or a seat taken back during its AI player's turn delay, whose turn opened with the reconnect, can be
  awaited, so the event carries how long its timer has run for the client's countdown.
  Beside the events the session writes replay-only annotation records, the seat control records, which
  follow who plays each seat:
  * an AI replacement goes in ahead of the AI player's moves, with its reason: `left` for a
    disconnect (a kick included), which may fall between rounds, during a round advance;
  * a seat with no connection at the start, never joined, is recorded `absent` after the deal and
    ahead of the dealer's first draw, the moves of the AI players seated from the start included, since
    its AI player holds it from the deal: the seat owes no confirmation, and its AI player plays its turns;
    a seat that leaves during the start's confirmation is recorded `left`, also ahead of that draw;
  * an AI player seated from the game's start has no seat control record: it never had a human;
  * a reconnect that takes the seat back from its AI player writes a human return;
  * a connection replacement writes nothing: its seat never left its human.

  The replay loader skips them; they only tell a viewer what happened.

* **Each task logs as its own subject.** A task copies the structlog context of whatever spawned
  it, often another seat's action, so a fired timer binds its game and its own seat, and the
  finalizer its game with no seat; a new background task rebinds its context the same way.
* **A graceful stop is a disconnect.** The manager has no drain of its own: a graceful stop ends
  games only through the normal leave of each closed socket, and `shutdown()` ends no game. A
  separate shutdown classification would need a drain signal ahead of the socket closes, which
  uvicorn does not give. The sequence is in `docs/architecture.md`.
