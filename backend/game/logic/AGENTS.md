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
* One dispatch pipeline for humans, AI and timeouts: `_dispatch_action()` picks the action handler
  (a player's action from `handle_action()`; an AI decision or timeout default through
  `_dispatch_generated_action()`, which turns any refusal into a fault), `_commit_and_process()`
  stores the result and runs what follows it (round end, post-discard calls and draw, chankan), and
  `_continue_with_ai_players()` → `_process_ai_player_followup()` runs the AI turns it leads to; AI
  call responses go through the same handlers (`_dispatch_ai_player_call_responses()`).
  `AIPlayerController` only decides (`get_turn_action`, `get_call_response`); every state change
  goes through `MahjongGameService`.
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
  discards the drawn tile). The discard validator, the turn timeout and the AI all go through them, and `can_call_chi`
  drops a shape that would leave no legal discard, so the default chooser never comes up empty; if it does, that is an
  engine fault (`AssertionError`), not a rule error.

## Calls

A discard creates one `PendingCallPrompt` (`call_type=DISCARD`) holding every eligible caller: ron
callers as `int`, meld callers as `MeldCaller`, and a seat eligible for both as a ron caller only.
A shouminkan that someone can rob, or an ankan that a kokushi hand can rob, creates a `CHANKAN`
prompt instead. Each response (including pass) removes the seat from
`pending_seats`; when it is empty, `call_resolution.resolve_call_prompt()` picks ron > pon/kan > chi
> pass. Dora reveal and riichi finalization after a discard wait until no ron is taken.

## Errors

Every refusal or failure has exactly one outcome (`exceptions.py` holds the classes):

* **ErrorEvent to the acting seat, nothing changes, the turn and its timer go on**: a rule judgment
  the client cannot make from the wire (`GameRuleError`: kuikae or riichi tsumogiri is
  `INVALID_DISCARD`, a riichi discard that breaks tenpai is `INVALID_RIICHI`), and a race the server
  can detect from state alone: any turn action, closed or added kan included, out of turn or while
  a call prompt is pending is `NOT_YOUR_TURN`; a call or pass with no prompt for the seat, or a call
  naming another tile, gets that call's code.
* **Kick**: structurally impossible input (a tile not in hand, an action, tile or chi shape the wire
  did not offer). Domain code raises `ImpossibleActionError`; only the handler validating the acting
  seat turns it into `InvalidGameActionError`, and the session disconnects that human (1008) and
  seats an AI player. A stale action from an earlier wait that lands on a newer one (a discard of a
  tile the turn timeout already discarded, a ron arriving at a later prompt where the seat may only
  meld) looks the same as bad input, because the wire carries no wait identity, so it is still
  kicked; telling them apart needs that identity on the wire.
* **Server fault, the session ends the game through `fail_game`**: everything else, with no blame
  guessing and no fabricated pass, win or retry. That covers wall and engine invariants
  (`AssertionError`), the scoring library failing on a hand judged a win (`ScoringError`), anything
  raised during call resolution (responses were validated on submit) or after a result is stored,
  and an action the server made itself: an AI decision or a timeout default that is refused, or an
  AI turn with no action, raises `GeneratedActionError` (`_dispatch_generated_action`), so a soft
  error never counts as AI progress.

Validation completes before a handler returns, and the service stores a result only after its
handler returned, so a refusal never leaves a partial state.

## Determinism

The same seed and inputs produce an identical replay trace. Randomness comes only from `rng.py`
(PCG64DXSM, seeded per round); AI strategies must be deterministic for a given state. A change to
wall or RNG behaviour bumps `RNG_VERSION`; a change to the replay format bumps `REPLAY_VERSION`
(`wire/replay_format.py`).
