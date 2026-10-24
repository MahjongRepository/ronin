# Game messaging (wire protocol)

Binary MessagePack frames only. The code is the protocol reference: client and session messages
with their codes in `types.py` and `wire_enums.py`, event and game error codes in `../wire/` and
`../logic/enums.py`, event fields as the serialization aliases on the event models in `../logic/`.
Inbound dispatch lives in `../server/router.py`; this package only models and shapes messages.

* Integer codes are only ever added, never renumbered or reused: a removed one leaves its gap.
* `event_payload.py` builds every outgoing event, for both the socket and the replay. A draw, a
  discard and a meld each pack into one integer (`../wire/compact.py`, `shared/lib/melds/README.md`).
* Delivery rules clients rely on: a draw goes only to the drawing seat, with its available actions
  when it has any; no draw follows the seat's own pon or chi, nor is one re-sent on a reconnect
  before that seat's discard; a discard's call prompt is split per seat; `furiten` goes only to its
  seat, and only on a change, so the `game_reconnected` snapshot carries the seat's current furiten.
* Wait identity: the message that opens a wait carries the current wait id, stamped at send time, and
  the reconnect snapshot always carries it. Every game action must echo it, and one for another wait
  is refused as stale. The replay collector shapes its own payloads, so live-only metadata like the
  wait id never reaches a replay file.
* The frontend mirrors this protocol in `frontend/game/src/shared/protocol/`; change both in the same
  change.
