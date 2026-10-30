# Session entity

One machine owns finding the handoff, joining, playing, reconnecting and the end.

- It joins with the lobby's ticket (`shared/session` holds the handoff) and resumes the seat with the same ticket. A
  tab that holds no ticket asks the lobby (`GET /api/game-session`) through an effect the driver runs and cancels on
  dispose: this game's handoff is kept and joined with, another game's kept and its page opened (the query, so
  `?v=2`, carried over), none sends the player to the lobby, and a failed lookup is asked once more after a short
  wait (`policy.ts`), then stays on the page with a reload.
- An active session is one of four states, each a variant of its own carrying only its own facts, so no combination
  of flags implies one: connecting (a socket asked for, with its connect deadline), identifying (the socket open and
  the identity message sent, JOIN_GAME or RECONNECT, with a session retry's due time or none), playing (the seat held:
  the only state that sends game messages, and the only one without an identity or retry count; whether it has seen
  the game start, its `game_started` or a snapshot, which a joined game waits for, its status saying so) and awaiting
  a transport retry (no socket, with its due time). Whether this page lost the seat it held belongs to the RECONNECT
  identity alone, so a join never has lost one; a drop before the game started joins again with JOIN_GAME, the only
  identity a game waiting to start takes (the server turns it into RECONNECT if the game started meanwhile). Only an
  open socket carries a message, so connecting and awaiting a retry ignore every one.
- Only the server's answer admits an identifying session (`game_joined` a JOIN_GAME, the snapshot a RECONNECT), never
  a game message. A refusal ends any active session; only identifying schedules identity retries:
  `join_game_already_started` turns a JOIN_GAME into RECONNECT and is ignored once the session reconnects or plays,
  and `reconnect_retry_later` (to a RECONNECT) and a rate limit schedule a session retry, as does `not_in_game` while
  identifying, which answers only an out-of-step client's resync request (`entities/client/AGENTS.md`, Desync) and
  says the server took no identity message on the socket; any other session error answering the identity message
  (all but `game_not_started`, which answers only an action or a resync request) ends the session as refused, so an
  unexpected answer never leaves it identifying for good. Any other handling of a session error (a rate limit or
  `game_not_started` answering a resync request or an action) is the client's.
- Two retries stay distinct, each with its own backoff and budget: a transport retry reopens a dropped socket, a
  session retry resends the identity message on the open socket. A drop supersedes a waiting session retry, since the
  reopened socket sends the identity message itself. A socket that has not opened by its connect deadline is closed
  and retried as a drop. Being out of step is the client state's, not the session's: it concerns the table the
  session's messages build, its resync requests are counted for the page across the session's admissions, and it
  ends by a snapshot the session takes like any other.
- The stop policy follows the server: the 4002 and 1008 closes, a refusal that means the ticket will never hold the
  seat again, and a spent retry budget end the session, cancel its retry and forget the handoff, and stay on the page,
  whose board says why with a way back; a game end ends it on the page and forgets the handoff, since its ticket will
  never hold the seat again; any other close is retried, 1000 included (`docs/architecture.md`, Game client
  contract). A valid input the machine has no transition for in its state changes nothing and asks for nothing. An
  ended session ignores everything after, except that leaving still goes to the lobby from an end that stayed on the
  page.
- Leaving while the session holds or works for the seat hands it to an AI, so the page asks first (`PlayUi`),
  modally: the rest of the page is inert, Stay is the primary action and takes the focus, Escape stays, and staying
  returns the focus to the control that asked; after an end it leaves at once.
