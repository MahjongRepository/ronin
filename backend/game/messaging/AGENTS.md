# Game messaging (wire protocol)

Binary MessagePack frames only. The code is the protocol reference: client and session messages
with their codes in `types.py` and `wire_enums.py`, event and game error codes in `../wire/` and
`../logic/enums.py`, event fields as the serialization aliases on the event models in `../logic/`.
Inbound dispatch lives in `../server/router.py`; this package only models and shapes messages.

* Integer codes are only ever added, never renumbered or reused: a removed one leaves its gap.
* `event_payload.py` builds every outgoing event, for both the socket and the replay. A draw, a
  discard and a meld each pack into one integer (`../wire/compact.py`, `shared/lib/melds/README.md`).
* Of `GameSettings` only the riichi stick value (`rsv`), a wire score, goes out live, on `game_started`
  and the reconnect snapshot: the one setting a client consumes, since every deposit and payment comes
  settled. The replay records every setting on its `game_started` line (`gs`) instead and drops it, so a
  replay reader takes it from `gs`.
* An accepted JOIN_GAME is answered by `game_joined` to the joining connection alone, ahead of anything
  the game sends it, as an accepted RECONNECT is by the snapshot; every refused one by a session error.
  So a client is admitted by the server's answer, never by inferring it from the game's messages.
  `game_joined` names the pending game's timeout (`pt`), the longest the server stays silent before the game
  starts, so a client's silence watchdog follows the server's pacing rather than a copy of its defaults.
* Delivery rules clients rely on: `game_started` is broadcast with each copy naming its recipient's
  seat (`s`) and timer settings (`tm`, which the reconnect snapshot carries too, with the seat's
  current bank; the client counts its own turns and the game start pause down from them), and the
  first deal follows it only after the session's game start pause; a draw (the deal's first, a
  replacement after a kan and an AI player's included) goes whole only to the drawing seat, with its
  available actions when it has any, and every other connected seat gets its draw notice in its
  place, shaped from the same engine draw (`draw_notice_payload`): the drawer's seat and the live wall
  left (`tr`), never the tile, the offers, the bank or a wait id, and a code of its own, so it never
  opens a decision. The
  replay records the draw once and no notice; a draw re-sent on a reconnect goes to its seat alone.
  No draw or notice follows the seat's own pon or chi: a
  `turn` event to that seat names the tile types kuikae forbids it to discard instead; the draw or
  `turn` event that opens a seat's turn names its bank as the turn's timer starts (`bk`), so the
  client's bank never drifts by delivery delays; a discard's
  call prompt is split per seat; after the `game_reconnected` snapshot a reconnect re-sends the
  event that opened the wait the game owes the seat (its draw, its `turn` event or its call
  prompt), with how long the wait's timer has run (`el`, seconds), and a resync request on the seat's
  own connection is answered with the same two; `furiten` goes only to its seat, and only on a change, so the `game_reconnected`
  snapshot carries the furiten last sent to the seat. Past rounds are never re-sent either, so the
  snapshot carries every finished round's ledger entry for the final standings. A robbed kan sends
  no meld event: the round end that robs it names it, and so does the snapshot's round result. A
  snapshot taken during a round advance shows the round that ended: its dealer, wind, round number,
  number within the wind and honba with its tiles, the scores and riichi sticks its result left, that result (`re`) in the
  round end's shape, and whether the seat still owes its confirmation (`oc`), with how long that
  wait's timer has run (`el`) and its whole timeout (`at`) only when the seat owes it and its timer
  is running. The round end that opens a
  round advance names that whole timeout too (`at`, seconds), so the client times the confirm by
  the server's word, never by its own count of the results. The snapshot names the seat of the round's latest
  discard (`ld`, from the engine's ordered discard history), which lies last in that seat's river and
  is kept through draws, kans from the hand and a pending result; it is absent, never null, before the
  round's first discard and once a call claimed that discard, never naming an earlier one. The snapshot gives
  each seat's closed-hand size, since a client sees other hands face down and never sees their
  tiles. A participant's seat changing hands goes to the others as `seat_control`, by seat and
  shaped like the replay's seat control line, ahead of the moves that follow; the snapshot marks a
  seat an AI player holds for its participant by why (`sr`), never as an AI player's (`ai`).
* What a client shows of the table's counts comes from the server, never the client's own arithmetic:
  the deal, each draw and its notice name the live wall left (`tr`); the deal and the snapshot name the
  round's number within its wind (`rw`, from 1) and the snapshot the game's first dealer (`fd`); an
  accepted riichi names its declarer's score after the deposit (`sc`) and the table's riichi sticks
  (`r`); a round end, and the snapshot's `re`, name the sticks its result leaves (`r`); a chankan
  prompt names the kan it offers to rob (`kty`, added or closed).
* What a client shows of a round's result comes from the server too, never its own table or the
  scoring rules worked backwards: a round end, and the snapshot's `re`, name the round's dealer (`dl`)
  and revealed dora indicators (`di`); a win's hand result the limit it was paid at (`lm`, with the
  yakuman count `yc` of a yakuman or kazoe yakuman) and each yaku's yakuman count (`ym`, 0 for an
  ordinary yaku); each winner its honba bonus (`hb`) and, beside its liable seat (`ps`), what that
  seat pays (`pl`: the pao yakuman, all or half, and whether the honba); a nagashi mangan each
  qualifying seat's river (`qr`). A round history entry carries no round number within its wind.
* Wait identity: the message that opens a wait carries the current wait id, stamped at send time, and
  the reconnect snapshot always carries it. Wait ids are one counter per game that only grows (the
  service bumps it by one per call that ends a wait, `MahjongGameService._end_call`), so across the
  frames that open a wait and the snapshots a seat receives the id never decreases: a new wait has
  a larger id, a re-send of the same wait (a reconnect, a resync) repeats it, and the waits of
  other seats leave gaps. Refusals are outside this order, since they echo the refused action's
  id. Every game action must echo it, and one for another wait
  is refused as stale. A refusal of a game action names the wait id that action echoed, never the
  current wait's: a game error (stale or a rule judgment) always, and the endpoint's rate limit when
  the frame it drops is a game action with a readable id, since that limit answers before any
  routing and can refuse an old frame after the game moved on. The client matches it to its own
  request; this is no request id, and a JOIN_GAME or RECONNECT refusal names none. The replay
  collector shapes its own payloads, so live-only metadata like the wait id never reaches a replay
  file.
* The game client mirrors this protocol in `frontend/game_v2/src/shared/protocol/`; update it with any server
  protocol change.
