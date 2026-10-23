# Game logic

The rules engine. `docs/game-rules.md` is the ruleset it implements (fixed mechanics and the configurable
`GameSettings`); read it before changing or testing a rule, and update it when a rule changes.

## Model

* State is frozen Pydantic (`state.py`), updated by copy with the helpers in `state_utils.py`; settings live only on
  the game state. One game state flows through the round-flow functions; only a helper scoped to a round or a player
  takes the round.
* A round ends only through `finish_round()` (`state_utils.py`), so a finished round always carries its result, and
  the result stays on the round through the round-advance wait.
* Domain events (`events.py`) carry integer tile ids only (136-format) and their own routing target, a broadcast or
  one seat.
* The game state's `wait_id` identifies the current wait and changes exactly when a call ends it
  (`mahjong_service.py` holds the rule); the session drives its timers from it and checks client actions against it,
  so the engine API carries no wire id.
* One dispatch pipeline for humans, AI and timeouts. A human's refused action is answered before the commit: nothing
  is stored and no AI turn runs. `AIPlayerController` only decides; every state change goes through
  `MahjongGameService`.
* Player type is a service-layer fact: the player model has no AI flag, only `AIPlayerController` knows. Names and
  AI flags go out once in `game_started`; later events use seats. `handle_action` and `handle_timeout` act only for
  a human seat; one for an AI seat is a server fault, since the session only ever acts for a connected human.
* The seat is a player's only identity: `start_game` returns each input player's seat and every later call takes a
  seat. Names are display only and nothing looks a player up by name; AI names skip the names in use without
  touching the RNG, so names stay unique for the replay format and the name-carrying session messages.
* Pacing (turn, bank, meld, round-advance and pending-game timeouts) is a session concern (`session/timer.py`),
  never a `GameSettings` field.
* Everything the engine keeps for one game is its `GameRuntime` (`runtime.py`), owned by the caller: dropping it
  disposes the game, so there is no game id registry, no cleanup call and no "game not found" path.

## Turn rules

* `get_available_actions` (`actions.py`) builds a turn's offered actions in one place, for the live draw event and
  the reconnect rebuild alike; each handler re-checks the predicate the offer used. Right after the player's own pon
  or chi nothing was drawn: only a discard is legal, and no draw is sent.
* `legal_discards` and `choose_default_discard` (`round.py`) are the one legal-discard rule, used by the discard
  validator, the turn timeout and the AI; the chi check drops a shape that would leave no legal discard, so the
  default chooser never comes up empty (if it does, that is an engine fault).
* "No call yet" is one predicate on the round state (closed kans count), shared by every rule that needs it. Four
  Winds alone looks only at open melds, so a closed kan does not prevent it.

## Calls

A discard, or a kan someone can rob, opens one `PendingCallPrompt` (`state.py`) that `call_resolution.py` resolves
once every eligible seat has answered. The rules the two share: a seat eligible for both ron and a meld is offered
ron only; the prompt's caller order is both the order clients get their prompts and the ron ranking; resolution picks
ron > pon/kan > chi > pass; dora reveal and riichi finalization after a discard wait until no ron is taken.

## Errors

Every refusal or failure has exactly one outcome; `exceptions.py` says which class lands where.

* **ErrorEvent to the acting seat, nothing changes, the turn and its timer go on**: a rule judgment the client cannot
  make from the wire, or a race the server can detect from state alone.
* **Kick**: structurally impossible input the wire never offered, raised only by the handler validating the acting
  seat; the session disconnects that human and seats an AI player. A stale action never reaches the engine: the
  session rejects it by wait id.
* **Server fault, the session ends the game**: everything else, with no blame guessing and no fabricated pass, win or
  retry. A refused action the server made itself (an AI decision or a timeout default) is a server fault, so a soft
  error never counts as AI progress.

Validation completes before a handler returns and the service stores only an `ActionResult`, so a refusal never
leaves a partial state.

## Determinism

The same seed and inputs produce an identical replay trace. Randomness comes only from `rng.py`: a SHAKE256 word
stream over the seed, with a separate domain per use (the wall of each round, the first dealer), read through rejection
sampling so no draw is biased; AI strategies must be deterministic for a given state. Seat assignment is part of the
contract: the replay loader inverts the seeded seat permutation to rebuild the input order, so a change to it is a
change to the replay format. A change to wall or RNG behaviour bumps `RNG_VERSION`; a change to the replay format
bumps `REPLAY_VERSION` (`wire/replay_format.py`).

## Tile ownership

* The dead wall (`wall.py`) is modelled by role, never by index: a rinshan queue, five indicator stacks whose top is the
  dora and bottom the ura, and a reserve for the live tiles pulled in after each kan. Dora and ura are derived from the
  same stack prefix, so they cannot drift apart; `DeadWall` validates its partition on every construction, and the wall
  functions construct it rather than `model_copy` it so the validator always runs.
* Every state the engine adopts goes through `GameRuntime.commit()`, which checks that hands, melds, unclaimed discards,
  the live wall and the dead wall own each of the 136 tiles exactly once (`invariants.py`). A failure is a server fault:
  nothing is repaired or retried. Never assign `runtime.state` directly. Tests that stage hands or walls on a runtime use
  the helpers in `tests/unit/helpers.py`, which restore ownership around what the test staged.
