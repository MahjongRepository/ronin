# Game logic

The rules engine. `docs/game-rules.md` is the ruleset it implements (fixed mechanics and the
configurable `GameSettings`); read it before changing or testing a rule, and update it when a rule
changes.

## Model

* State is frozen Pydantic (`state.py`: `MahjongGameState` → `MahjongRoundState` → `MahjongPlayer`,
  plus `PendingCallPrompt`); update with `model_copy(update=...)` and the helpers in
  `state_utils.py`. Settings live only on `MahjongGameState`. The wall is a frozen `Wall`
  (`wall.py`); melds are `FrozenMeld` (`meld_wrapper.py`), converted to the `mahjong` library's
  `Meld` only at its boundary.
* Domain events (`events.py`) carry integer tile ids only (136-format); `convert_events()` wraps
  them in `ServiceEvent` with a `BroadcastTarget` or `SeatTarget`.
* One dispatch pipeline for humans and AI: `handle_action()` → `_dispatch_and_process()` → action
  handlers, then `_process_ai_player_followup()` runs AI turns and call responses through the same
  handlers. `AIPlayerController` only decides (`get_turn_action`, `get_call_response`); every state
  change goes through `MahjongGameService`.
* Player type is a service-layer fact: `MahjongPlayer` has no AI flag, only
  `AIPlayerController.is_ai_player(seat)` knows. Names and AI flags go out once in `game_started`;
  later events use seats.
* Per-game side state lives in narrow trackers with a `cleanup_game()`: `FuritenTracker` (emits
  `FuritenEvent` on change) and `RoundAdvanceManager` (who still has to confirm the round end; AI
  seats are pre-confirmed).

## Turn rules

* `get_available_actions` (`actions.py`) builds a turn's offered actions (riichi, tsumo, kan, kyuushu) in one
  place, for the live draw event and the reconnect rebuild alike; each handler re-checks the same predicate the offer
  used. Right after the player's own pon or chi (`is_after_meld_call`) nothing was drawn: only a discard is legal, and
  no draw is sent or rebuilt.
* `legal_discards` and `choose_default_discard` (`round.py`) are the one legal-discard rule (kuikae; a riichi player
  discards the drawn tile). The discard validator, the turn timeout, the AI and its fallback all go through them, and
  `can_call_chi` drops a shape that would leave no legal discard, so the default chooser never comes up empty; if it
  does, that is an engine fault (`AssertionError`), not a rule error.

## Calls

A discard creates one `PendingCallPrompt` (`call_type=DISCARD`) holding every eligible caller: ron
callers as `int`, meld callers as `MeldCaller`, and a seat eligible for both as a ron caller only.
A shouminkan that someone can rob, or an ankan that a kokushi hand can rob, creates a `CHANKAN`
prompt instead. Each response (including pass) removes the seat from
`pending_seats`; when it is empty, `call_resolution.resolve_call_prompt()` picks ron > pon/kan > chi
> pass. Dora reveal and riichi finalization after a discard wait until no ron is taken.

## Errors

Rule violations raise `GameRuleError` subclasses (`exceptions.py`), never a bare `ValueError`, and
handlers turn them into an `ErrorEvent`. A provably invalid action (data a real client could not
send) raises `InvalidGameActionError` with the offending `seat`, which may differ from the acting
seat when call resolution fails on another player's earlier response; the session layer disconnects
that seat and seats an AI player.

## Determinism

The same seed and inputs produce an identical replay trace. Randomness comes only from `rng.py`
(PCG64DXSM, seeded per round); AI strategies must be deterministic for a given state. A change to
wall or RNG behaviour bumps `RNG_VERSION`; a change to the replay format bumps `REPLAY_VERSION`
(`wire/replay_format.py`).
