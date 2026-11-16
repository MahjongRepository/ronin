# Game logic

The rules engine. `docs/game-rules.md` is the ruleset it implements (fixed mechanics and the `GameSettings` values
of its one preset); read it before changing or testing a rule, and update it when a rule changes. Outside code
reaches it only through `game.engine`, whose seam invariants every change here keeps (`../engine/AGENTS.md`).

## Model

* State (`state.py`) is updated by copy with the helpers in `state_utils.py`; settings live only on
  the game state. One game state flows through the round-flow functions; only a helper scoped to a round or a player
  takes the round.
* A round ends only through `finish_round()` (`state_utils.py`), so a finished round always carries its result, and
  the result stays on the round while the game waits on its end (`RoundOver`). It also appends the round's compact ledger entry to the
  game state's `round_history`, the one record of past rounds (a seat's view carries it).
* Domain events (`events.py`) carry 136-format tile ids, and domain models keep readable field names and domain
  melds (`FrozenMeld`); an import-linter contract keeps `shared.lib` out, so no wire encoding creeps in.
* The pending call prompt and its ron ranking stay in state and are never emitted.
* The view (`view.py`) is built from state and the furiten tracker. While the game waits on a round's end the
  header is the ended round's, read back from its round history entry since the round end already moved the table
  on, and the furiten is the tracker's last report to the seat.
* The preset is profile 1 in `rule_profiles.py`, a frozen value that explicitly supplies every setting, independent
  of `GameSettings` defaults. `GameSettings` stays inside the engine for its mechanics and its own tests, which stage
  other values on the state. While stored replays are only test games, a rule change edits the preset in place,
  since playback reads recorded events and not the preset. A new setting needs a deliberate preset value, and no
  pacing duration is ever one.
* Everything the engine keeps for one game is its `GameRuntime` (`runtime.py`), owned by the caller: dropping it
  disposes the game, so there is no game id registry, no cleanup call and no "game not found" path.

## Turn rules

* Actions and decisions are domain values (`decision.py`): an action names physical tile ids and never a wire code,
  a wait id or a call's tile (a pon or chi answers the open call; the session checks a message's called tile).
  `build_decision` (`actions.py`) derives a seat's legal actions and default from the same offer code the handlers
  re-check, so the two cannot drift; legality is equivalence, not equality with a listed entry (a chi with another held
  copy of an offered shape, a kan from any tile of an offered type). The default is never a win or a call.
* `get_available_actions` (`actions.py`) builds a turn's offered actions in one place, which the decision lists after
  the legal discards; each handler re-checks the predicate the offer used. Riichi lists the discards that keep tenpai.
  A draw never offers a discard: any tile in hand is legal, in riichi only the drawn one, except right after the
  player's own pon or chi, when nothing was drawn and the decision names the tile types kuikae forbids.
* `legal_discards` and `choose_default_discard` (`round.py`) are the one legal-discard rule, used by the discard
  validator and a turn decision's default; the chi check mirrors its non-riichi kuikae rule itself (a riichi seat
  cannot chi) and drops a shape that would leave no legal discard, so the default chooser never comes up empty (if
  it does, that is an engine fault).
* "No call yet" is one predicate on the round state (closed kans count), shared by every rule that needs it.

## Calls

A discard, or a kan someone can rob, opens one `PendingCallPrompt` (`state.py`) that `call_resolution.py` resolves
once every eligible seat has answered. The rules the two share: a seat eligible for both ron and a meld is offered
both, in one call decision that lists its ron and its melds, and a meld it makes instead declines the ron (the furiten
of a pass, applied where the response is recorded), while a seat the discard completes but which cannot ron is made
furiten at the discard itself, prompt or not; the prompt's caller order is the ron ranking; resolution picks ron >
pon/kan > chi > pass; a deferred kan dora is revealed at the discard, before ron is judged; riichi finalization and then the four riichi and four kans aborts wait until no ron is taken. One step (`pass_ron_window`) runs them, before a meld on
the discard executes, for the no-caller path and at resolution alike; the four kans check alone withholds meld offers on
the fourth kan's replacement discard. A kan never ends the round itself: the four kans abort is its replacement
discard's. A closed or added kan runs the same executor declared directly or completed after its robbers declined, and
every kan emits its one rinshan draw there; the engine also draws for the next seat itself, so the service adds no draw.

## Errors

The engine never raises for a player's input: `act`, `begin_round` and `deal_next_round` return a `Refusal`
(`refusal.py`) that changed nothing, its kind set by the handler that rejects the action and its code a reason, never a
wire code. What a refusal leads to (an error to the seat, a kick, a failed game) is the caller's policy; the wire code
and message are messaging's.

* **RULE**: a rule judgment on a held tile or an offered action, a discard's kuikae and riichi rules included although
  the client is told them (a `GameRuleError` subclass in `exceptions.py`, each with its code).
* **NOT_OFFERED**: structurally impossible input the seat was never offered, a tile not held included, caught only by
  the handler validating the acting seat (`ImpossibleActionError` and its subclasses). Raised anywhere else (call
  resolution executes answers already validated) it stays an exception and a server fault.
* **NOT_AWAITED**: a phase call in the wrong phase, an action while the round is not in play, from a seat the engine
  is not waiting on, or for another decision than the seat's (a pass on its own turn, a discard during a call), a race
  the server can detect from state alone.
* **Server fault**: everything else raises, with no blame guessing and no fabricated pass, win or retry.

Validation completes before a handler returns and the service stores only an `ActionResult`, so a refusal never
leaves a partial state.

## Determinism

The same seed and inputs produce an identical replay trace. Randomness comes only from `rng.py` (`docs/rng.md`). The
seed's seat permutation is the contract for live seating only: the session seats its players by it (`docs/rng.md`),
while a replay records each seat's name, which the loader seats as recorded. A change to wall or RNG behaviour bumps
`RNG_VERSION`; a change to the replay format bumps `REPLAY_VERSION` (`wire/replay_format.py`).

## Tile ownership

* The dead wall (`wall.py`) is modelled by role, never by index: a rinshan queue, five indicator stacks whose top is the
  dora and bottom the ura, and a reserve for the live tiles pulled in after each kan. Dora and ura are derived from the
  same stack prefix, so they cannot drift apart. `DeadWall` validates its partition and `Wall` that the live wall is
  disjoint from it on every construction; the wall functions construct both rather than `model_copy` them so the
  validators run whenever the partition changes. The one exception is a plain draw, which `model_copy`s the wall
  without its first live tile: removing a prefix from a validated live wall cannot break a validator, and the dead
  wall is the same object. The ownership check does not cover a skipped validator: it does not check the dead wall's
  role counts.
* Every state the engine adopts goes through `GameRuntime.commit()`, which checks that hands, melds, unclaimed discards,
  the live wall and the dead wall own each of the 136 tiles exactly once (`invariants.py`). A failure is a server fault:
  nothing is repaired or retried. `runtime.state` is read-only, so `commit()` is the only way to replace it. Tests
  that stage hands or walls on a runtime use the helpers in `tests/unit/logic/helpers.py`, which restore ownership around
  what the test staged and commit the result.
