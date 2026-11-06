# Game messaging (wire protocol)

Binary MessagePack frames only. The code is the protocol reference: client and session messages
with their codes in `types.py` and `wire_enums.py`, event and game error codes in `../wire/` and
`../logic/enums.py`, event fields in `event_payload.py` and `serialization.py`.
Inbound dispatch lives in `../server/router.py`; this package only models and shapes messages.

* Integer codes are only ever added, never renumbered or reused: a removed one leaves its gap.
* Live metadata map keys are integers in both directions. `wire/keys.py` owns the named `WireKey`
  IDs; numeric IDs appear only in that declaration, and callers use the named keys directly.
  Outgoing serializers explicitly build numeric-key maps from domain model attributes. Incoming parsing extracts
  numeric keys into typed models with readable fields. `encoder.py` validates and packs those maps without translating
  keys, and decoding preserves the numeric keys. Score maps keep string seat keys as data. Unknown, duplicate or malformed keys
  are rejected, with the existing message-size limits and a nesting bound; decode failures still pass
  through the endpoint's rate-limit and strike handling. The browser and external bot mirror the same
  registry and shared golden frames; protocol changes update all three together. Replay IDs keep their
  existing assignments, and replay-only metadata is not accepted on the live wire.
* `event_payload.py` builds every outgoing event, for both the socket and the replay. Its
  `live_game_event_payload` removes the per-draw wall count for normal delivery and reconnect resends;
  the replay keeps the engine's explicit count. A draw, a
  discard and a meld each pack into one integer (`../wire/compact.py`, `shared/lib/melds/README.md`).
* Of `GameSettings` only the game type (`WireKey.GAME_TYPE`) and the riichi stick value (`WireKey.RIICHI_STICK_VALUE`), a wire
  score, go out live, on `game_started` and the reconnect snapshot: the settings a client consumes, the type for its
  headings and the stick value since every deposit and payment comes settled. Replay game-start records retain this viewing value and an explicit aka-dora flag; their
  compact `WireKey.GAME_SETTINGS` profile reference resolves the full effective settings for Python consumers.
* An accepted JOIN_GAME is answered by `game_joined` to the joining connection alone, ahead of anything
  the game sends it, as an accepted RECONNECT is by the snapshot; every refused one by a session error.
  So a client is admitted by the server's answer, never by inferring it from the game's messages.
  `game_joined` names the pending game's timeout (`WireKey.PENDING_GAME_TIMEOUT`), the longest the server stays silent before the game
  starts, so a client's silence watchdog follows the server's pacing rather than a copy of its defaults.
* Delivery rules clients rely on: `game_started` is broadcast with each copy naming its recipient's
  seat (`WireKey.SEAT`) and timer settings (`WireKey.TIMER_SETTINGS`, which the reconnect snapshot carries too, with the seat's
  current bank; the client counts its turns and calls down from them), and the
  first deal follows it at once: with the game start's confirmation (a round advance, `WireKey.GAME_START_CONFIRM` its
  timeout in the timer settings) each awaited seat's deal is stamped with its wait id and the confirmation's whole
  timeout (`WireKey.ROUND_ADVANCE_SECONDS`), the seat answers CONFIRM_ROUND, and the dealer's first draw follows once
  every awaited seat confirmed or the timeout confirmed for it; a later deal never carries either; a draw (the deal's first, a
  replacement after a kan and an AI player's included) goes whole only to the drawing seat, with its
  available actions when it has any, and every other connected seat gets its draw notice in its
  place, shaped from the same engine draw (`draw_notice_payload`): only the drawer's seat,
  never the tile, the offers, the bank or a wait id, and a code of its own, so it never
  opens a decision. The
  replay records the draw once and no notice; a draw re-sent on a reconnect goes to its seat alone.
  No draw or notice follows the seat's own pon or chi: a
  `turn` event to that seat names the tile types kuikae forbids it to discard instead; each draw, `turn` event or call prompt that opens a decision names its bank as the timer starts (`WireKey.BANK_SECONDS`),
  so the client's bank never drifts by delivery delays; a discard's
  call prompt is split per seat; after the `game_reconnected` snapshot a reconnect re-sends the
  event that opened the wait the game owes the seat (its draw, its `turn` event or its call
  prompt), with how long the wait's timer has run (`WireKey.WAIT_ELAPSED`, seconds), and a resync request on the seat's
  own connection is answered with the same two; `furiten` goes only to its seat, and only on a change, so the `game_reconnected`
  snapshot carries the furiten last sent to the seat. Past rounds are never re-sent either, so the
  snapshot carries every finished round's ledger entry for the final standings. A robbed kan sends
  no meld event: the round end that robs it names it, and so does the snapshot's round result. A
  snapshot taken during a round advance shows the round that ended: its dealer, wind, round number,
  number within the wind and honba with its tiles, the scores and riichi sticks its result left, that result (`WireKey.ROUND_RESULT`) in the
  round end's shape (none for the game start's confirmation, whose snapshot shows the dealt round before the dealer's draw), and whether the seat still owes its confirmation (`WireKey.CONFIRMATION_OWED`), with how long that
  wait's timer has run (`WireKey.WAIT_ELAPSED`) and its whole timeout (`WireKey.ROUND_ADVANCE_SECONDS`) only when the seat owes it and its timer
  is running. The round end that opens a
  round advance names that whole timeout too (`WireKey.ROUND_ADVANCE_SECONDS`, seconds), so the client times the confirm by
  the server's word, never by its own count of the results. The snapshot names the seat of the round's latest
  discard (`WireKey.LATEST_DISCARD_SEAT`, from the engine's ordered discard history), which lies last in that seat's river and
  is kept through draws, kans from the hand and a pending result; it is absent, never null, before the
  round's first discard and once a call claimed that discard, never naming an earlier one. The snapshot gives
  each seat's closed-hand size, since a client sees other hands face down and never sees their
  tiles. A participant's seat changing hands goes to the others as `seat_control`, by seat and
  shaped like the replay's seat control line, ahead of the moves that follow; the snapshot marks a
  seat an AI player holds for its participant by why (`WireKey.STAND_IN_REASON`), never as an AI player's (`WireKey.AI_PLAYER`).
* The deal and reconnect/resync snapshot provide the authoritative live-wall count (`WireKey.TILES_REMAINING`).
  Clients subtract one for each genuine private draw or public notice, including a kan replacement;
  a pending private draw re-sent after a snapshot is already counted and subtracts nothing. Neither
  pon/chi nor a robbed kan produces a draw. An impossible decrement is a desync, recovered by a snapshot.
  Replay draws retain their explicit counts. Other displayed counts still come from the server:
  the deal and the snapshot name the
  round's number within its wind (`WireKey.ROUND_IN_WIND`, from 1) and the snapshot the game's first dealer (`WireKey.FIRST_DEALER`); an
  accepted riichi names its declarer's score after the deposit (`WireKey.SCORE`) and the table's riichi sticks
  (`WireKey.RIICHI_STICKS`); a round end, and the snapshot's `WireKey.ROUND_RESULT`, name the sticks its result leaves (`WireKey.RIICHI_STICKS`); a chankan
  prompt names the kan it offers to rob (`WireKey.KAN_TYPE`, added or closed).
* What a client shows of a round's result comes from the server too, never its own table or the
  scoring rules worked backwards: a round end, and the snapshot's `WireKey.ROUND_RESULT`, name the round's dealer (`WireKey.DEALER`)
  and revealed dora indicators (`WireKey.DORA_INDICATORS`); a win's hand result the limit it was paid at (`WireKey.HAND_LIMIT`, with the
  yakuman count `WireKey.YAKUMAN_COUNT` of a yakuman or kazoe yakuman) and each yaku's yakuman count (`WireKey.YAKU_YAKUMAN_COUNT`, 0 for an
  ordinary yaku); each winner its honba bonus (`WireKey.HONBA_BONUS`) and, beside its liable seat (`WireKey.PAO_SEAT`), what that
  seat pays (`WireKey.PAO_LIABILITY`: the pao yakuman, all or half, and whether the honba); a nagashi mangan each
  qualifying seat's river (`WireKey.QUALIFYING_RIVERS`). A round history entry carries no round number within its wind.
* Wait identity: the wire `WireKey.WAIT_ID` is a participant's decision counter, starting at zero and increasing
  once for each new decision opened for that connected participant, round confirmations included.
  Other seats' waits and decisions made by an AI stand-in never advance it. Reconnect and resync
  snapshots carry the participant's latest id, even when nothing is owed; re-sending an owed
  decision repeats that id. Round-end broadcasts are stamped separately for each recipient.
  The engine's global wait counter stays server-only: neither outgoing metadata nor action
  refusals may reveal it. Refusals echo the refused action's id and sit outside the increasing
  order. Every game action must echo its own decision id; a seat that owes no action or an action
  with any other id is refused as stale, without consulting the engine. A refusal names the id that action echoed, never the
  current wait's: a game error (stale or a rule judgment) always, and the endpoint's rate limit when
  the frame it drops is a game action with a readable id, since that limit answers before any
  routing and can refuse an old frame after the game moved on. The client matches it to its own
  request; this is no request id, and a JOIN_GAME or RECONNECT refusal names none. The replay
  collector shapes its own payloads, so live-only metadata like the wait id never reaches a replay
  file.
* The game client mirrors this protocol in `frontend/game_v2/src/shared/protocol/`; update it with any server
  protocol change.
