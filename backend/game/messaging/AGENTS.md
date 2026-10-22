# Game messaging (wire protocol)

Binary MessagePack frames only. The code is the protocol reference: client messages, session
messages and error codes in `types.py`, client codes in `wire_enums.py`, event codes in
`../wire/enums.py` (mapped from `EventType` in `../wire/events.py`), event fields in the
`serialization_alias` keys of `../logic/events.py` and `../logic/types.py`. Inbound dispatch
(`MessageRouter`) lives in `../server/router.py`; this package only models and shapes messages.

* Client messages carry an integer `t` (`WireClientMessageType`); game actions add an integer `a`
  (`WireGameAction`) and short keys (`ti` for a tile id). Session messages from the server carry a
  string `type`; game events carry an integer `t` (`WireEventType`, mapped through
  `EVENT_TYPE_INT`). Integer codes are only ever added, never renumbered.
* `event_payload.py` builds every outgoing event, for both the socket and the replay:
  `model_dump(by_alias=True, exclude_none=True)` for most; draw and discard pack into one integer
  `d` (`../wire/compact.py`: `seat * 136 + tile_id`, discard adds `flag * 544` for tsumogiri/riichi); a meld
  is one IMME integer `m` (`shared/lib/melds/README.md`); `round_end` inlines its result with `rt`.
* Delivery rules clients rely on: a draw goes only to the drawing seat, with `aa` (available
  actions) when it has any; no draw follows a pon or chi, nor is one re-sent on a reconnect before
  that seat's discard; a discard's call prompt is split per seat and a seat that can both ron and
  meld gets only the ron prompt; `furiten` goes only to its seat, and only on a change, so the
  `game_reconnected` snapshot carries the seat's current furiten.
* The frontend mirrors this protocol in `frontend/src/shared/protocol/`; change both in the same
  change.
