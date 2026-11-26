# Session entity

One machine owns finding the handoff, joining, playing, reconnecting and the end.

- Credentials come only from the lobby's handoff in the tab's session storage or its recovery endpoint, never the URL.
- Every JOIN_GAME and RECONNECT of a handoff sends its seat claim unchanged; only a new handoff (a recovery) makes a
  new claim, so automatic retries never take a seat back from a newer claim (`docs/architecture.md`, Seat claims).
- Each state is a variant carrying only its own facts. Other slices ask the session through the queries its `index.ts` exports, never
  read its status, identity or retry fields; a new need is a new query here, its words stay the asker's.
- Only the server's answer admits an identifying session (`game_joined` for JOIN_GAME, the snapshot for RECONNECT),
  never other game traffic. An unexpected answer to the identity message ends the session as refused, so it never
  stays identifying.
- Before the game starts, a dropped seat rejoins with JOIN_GAME; answered `join_game_already_started`, the session
  sends RECONNECT on the same socket.
- A session error answering an action or a resync request (a rate limit, `game_not_started`) is the client's: never
  resend the identity for it.
- A transport retry (reopen a dropped socket) and a session retry (resend the identity on the open socket) are
  distinct, each with its own backoff and budget; a drop supersedes a waiting session retry.
- Being out of step is the client's, not the session's.
- Stop policy follows `docs/architecture.md` (Game client contract); `model/policy.ts` and `forgetsHandoff`
  (`model/transition.ts`) are its code.
- Leaving while the seat is held hands it to an AI, so the page asks first; Stay is the primary action.
