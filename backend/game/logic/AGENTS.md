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
* One state flows through a round: the round-flow functions (handlers, `turn.py`, `call_resolution.py`, scoring,
  draws) take and return the `MahjongGameState` alone and read its `round_state`, putting a changed round back with
  `update_game_with_round`; helpers whose scope is a round or a player (`draw_tile`, `discard_tile`, `call_pon`, the
  `can_*` predicates) take the round. A handler returns an `ActionResult` (its events and the one new state) or a
  `Refusal`.
* A round ends only through `finish_round()` (`state_utils.py`), which sets `phase=FINISHED` and the round's `result`
  together and returns the `RoundEndEvent` for the caller to append where the round ended. The service handles the
  round end when the stored round carries a result; the result stays through the round-advance wait, and `init_round`
  starts the next round without one.
* Domain events (`events.py`) carry integer tile ids only (136-format) and their own routing
  target, a `BroadcastTarget` or a `SeatTarget`; `ServiceEvent` wraps one and reads its type and
  target from it.
* Every `GameService` call that can change a game returns what the game waits for next
  (`Awaiting`: a turn, a call prompt, round-end confirmations, or nothing once the game is over,
  with the awaited seats AI players do not hold and the round the wait belongs to);
  `get_awaiting()` answers the same for a reconnect. Its `wait_id` lives on `MahjongGameState` and
  changes exactly when a call ends the current wait: `_end_call()` keeps it when the wait is of the
  same kind and either lost seats (a partial prompt response or confirmation, an AI answering for a
  replaced seat) or kept its seats on an untouched state (an error, a no-op timeout or
  replacement); anything else bumps it once, a turn that came back to the same seat and a kan's
  replacement draw included. The session drives its timers from it and checks client actions
  against it, so the engine API carries no wire id.
* One dispatch pipeline for humans, AI and timeouts: `_dispatch_action()` picks the action handler
  (a player's action from `handle_action()`; an AI decision or timeout default through
  `_dispatch_generated_action()`, which turns any refusal into a fault), `_commit_and_process()`
  stores the result and runs what follows it (the round end; the AI seats' answers to a call prompt left pending,
  a discard's or a kan's chankan alike; the draw after a discard nobody can call), and
  `_continue_with_ai_players()` → `_process_ai_player_followup()` runs the AI turns it leads to; AI
  call responses go through the same handlers (`_dispatch_ai_player_call_responses()`). A human's refused action
  is answered before the commit: nothing is stored and no AI turn runs.
  `AIPlayerController` only decides (`get_turn_action`, `get_call_response`); every state change
  goes through `MahjongGameService`.
* Player type is a service-layer fact: `MahjongPlayer` has no AI flag, only
  `AIPlayerController.is_ai_player(seat)` knows. Names and AI flags go out once in `game_started`;
  later events use seats. `handle_action` and `handle_timeout` act only for a human seat: one for a
  seat an AI player controls is a server fault (`AssertionError`), since the session only ever acts
  for a connected human.
* The seat is a player's only identity. `start_game` returns `GameStart` with each input player's seat
  in input order (the `fill_seats` sample, which the replay loader inverts, so it never changes), and
  every later call takes a seat. Names are display only: nothing looks a player up by name, and AI
  names ("Tsumogiri N") skip the names in use without touching the RNG, so names in a game stay unique
  for the replay format and the name-carrying session messages.
* The engine never suspends: no asyncio, no clock. Every `GameService` method is synchronous and returns
  with its state committed, so a caller needs no liveness re-check around an engine call. Pacing (turn,
  bank, meld, round-advance and pending-game timeouts) is a session concern (`session/timer.py`), never a
  `GameSettings` field.
* The service holds no game. Everything the engine keeps for one game is its `GameRuntime`
  (`runtime.py`): the frozen state (the only part that is a snapshot; the runtime itself is mutated
  in place), the `AIPlayerController`, the round's `FuritenTracker` (emits `FuritenEvent` on change,
  replaced at each round start) and `pending_confirm`, the round end's `PendingRoundAdvance` (the
  human seats still to confirm; AI seats never confirm), None otherwise. `start_game` builds it
  locally and returns it in `GameStart`, so a start that raises leaves nothing behind; every later
  call takes it. The caller owns it, and dropping it disposes the game: there is no game id
  registry, no cleanup call and no "game not found" path.

## Turn rules

* `get_available_actions` (`actions.py`) builds a turn's offered actions (riichi, tsumo, kan, kyuushu) in one
  place, for the live draw event and the reconnect rebuild alike; each handler re-checks the same predicate the offer
  used. Right after the player's own pon or chi (`is_after_meld_call`) nothing was drawn: only a discard is legal, and
  no draw is sent or rebuilt.
* `legal_discards` and `choose_default_discard` (`round.py`) are the one legal-discard rule (kuikae; a riichi player
  discards the drawn tile). The discard validator, the turn timeout and the AI all go through them, and `can_call_chi`
  drops a shape that would leave no legal discard, so the default chooser never comes up empty; if it does, that is an
  engine fault (`AssertionError`), not a rule error.
* "No call yet" is one predicate, `MahjongRoundState.has_any_call()` (closed kans count): tenhou, chiihou, renhou,
  double riichi and kyuushu kyuuhai all use it. Four Winds alone looks only at open melds (`has_open_melds()`), so a
  closed kan does not prevent it.

## Calls

A discard creates one `PendingCallPrompt` (`kind=PromptKind.DISCARD`) holding every eligible seat
as one `Caller`: a ron caller (`can_ron`) or a meld caller with its `MeldOption`s (kan > pon > chi);
a seat eligible for both is a ron caller only. A shouminkan that someone can rob, or an ankan that
a kokushi hand can rob, creates a `CHANKAN` prompt instead, every caller a ron caller.
`build_call_prompt_events()` turns each caller into its per-seat call prompt event (`CallType` RON,
MELD or CHANKAN) in the prompt's caller order, which is the order clients get them;
`_resolve_ron_responses` ranks ron winners by that same order. Each response (including pass) removes the seat from
`pending_seats`; when it is empty, `call_resolution.resolve_call_prompt()` picks ron > pon/kan > chi
> pass. Dora reveal and riichi finalization after a discard wait until no ron is taken.

## Errors

Every refusal or failure has exactly one outcome (`exceptions.py` holds the classes):

* **ErrorEvent to the acting seat, nothing changes, the turn and its timer go on**: the handler returns a
  `Refusal` (its code and message) and the service answers the seat with the ErrorEvent. It covers a rule judgment
  the client cannot make from the wire (`GameRuleError`: kuikae or riichi tsumogiri is
  `INVALID_DISCARD`, a riichi discard that breaks tenpai is `INVALID_RIICHI`), and a race the server
  can detect from state alone: any turn action, closed or added kan included, out of turn or while
  a call prompt is pending is `NOT_YOUR_TURN`; a call or pass with no prompt for the seat, or a call
  naming another tile, gets that call's code.
* **Kick**: structurally impossible input (a tile not in hand, an action, tile or chi shape the wire
  did not offer). Domain code raises `ImpossibleActionError`; only the handler validating the acting
  seat turns it into `InvalidGameActionError`, and the session disconnects that human (1008) and
  seats an AI player. A stale action, one answering a wait that already ended (a discard racing its
  own turn timeout, a pass or ron arriving after a newer prompt opened), never reaches the engine:
  every action echoes the wait id, and the session answers a stale one with `STALE_ACTION`.
* **Server fault, the session ends the game through `fail_game`**: everything else, with no blame
  guessing and no fabricated pass, win or retry. That covers wall and engine invariants
  (`AssertionError`), the scoring library failing on a hand judged a win (`ScoringError`), anything
  raised during call resolution (responses were validated on submit) or after a result is stored,
  and an action the server made itself: an AI decision or a timeout default that is refused (a `Refusal` or
  an `InvalidGameActionError`), or an AI turn with no action, raises `GeneratedActionError`
  (`_dispatch_generated_action`), so a soft error never counts as AI progress.

Validation completes before a handler returns, and the service stores only an `ActionResult`, after its handler
returned, so a refusal never leaves a partial state.

## Determinism

The same seed and inputs produce an identical replay trace. Randomness comes only from `rng.py`
(PCG64DXSM, seeded per round); AI strategies must be deterministic for a given state. A change to
wall or RNG behaviour bumps `RNG_VERSION`; a change to the replay format bumps `REPLAY_VERSION`
(`wire/replay_format.py`).
