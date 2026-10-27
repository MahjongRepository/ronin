# Game messaging (wire protocol)

Binary MessagePack frames only. The code is the protocol reference: client and session messages
with their codes in `types.py` and `wire_enums.py`, event and game error codes in `../wire/` and
`../logic/enums.py`, event fields as the serialization aliases on the event models in `../logic/`.
Inbound dispatch lives in `../server/router.py`; this package only models and shapes messages.

* Integer codes are only ever added, never renumbered or reused: a removed one leaves its gap.
* `event_payload.py` builds every outgoing event, for both the socket and the replay. A draw, a
  discard and a meld each pack into one integer (`../wire/compact.py`, `shared/lib/melds/README.md`).
* Delivery rules clients rely on: `game_started` is broadcast with each copy naming its recipient's
  seat (`s`) and timer settings (`tm`, which the reconnect snapshot carries too, with the seat's
  current bank; the client counts its own turns, the game start pause and the round results down
  from them), and the
  first deal follows it only after the session's game start pause; a draw goes only to the drawing
  seat, with its available actions when it has any; no draw follows the seat's own pon or chi: a
  `turn` event to that seat names the tile types kuikae forbids it to discard instead; the draw or
  `turn` event that opens a seat's turn names its bank as the turn's timer starts (`bk`), so the
  client's bank never drifts by delivery delays; a discard's
  call prompt is split per seat; after the `game_reconnected` snapshot a reconnect re-sends the
  event that opened the wait the game owes the seat (its draw, its `turn` event or its call
  prompt), with how long the wait's timer has run (`el`, seconds); `furiten` goes only to its seat, and only on a change, so the `game_reconnected`
  snapshot carries the furiten last sent to the seat. Past rounds are never re-sent either, so the
  snapshot carries every finished round's ledger entry for the final standings. A robbed kan sends
  no meld event: the round end that robs it names it, and so does the snapshot's round result. A
  snapshot taken during a round advance shows the round that ended: its dealer, wind, round number
  and honba with its tiles, the scores and riichi sticks its result left, that result (`re`) in the
  round end's shape, and whether the seat still owes its confirmation (`oc`), with how long that
  wait's timer has run (`el`) when it does. The snapshot gives
  each seat's closed-hand size, since a client sees other hands face down and never sees their
  draws.
* Wait identity: the message that opens a wait carries the current wait id, stamped at send time, and
  the reconnect snapshot always carries it. Every game action must echo it, and one for another wait
  is refused as stale. The replay collector shapes its own payloads, so live-only metadata like the
  wait id never reaches a replay file.
* The game client mirrors this protocol in `frontend/game/src/js/ronin/`; change both in the same
  change.
