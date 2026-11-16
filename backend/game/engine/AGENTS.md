# Engine facade

`game.engine` is the seam between the rules engine (`game.logic`) and everything that manages a game: the
session, messaging, wire, the replay tools, `scripts/` and `bin/`. Its `__init__.py` re-exports engine names
explicitly through `__all__`; it holds no wrappers, no logic of its own and no re-exported modules, and the
types stay defined in `game.logic`.

## Import rule

* Code outside `game.logic` imports the engine only from `game.engine`, `if TYPE_CHECKING:` imports included,
  though the lint graph leaves those out. A protected import-linter contract (`backend/pyproject.toml`) allows
  only this package, the engine-internal tests (`game/tests/unit/logic/`) and the test helpers that stage
  engine state to import `game.logic`.
* A test of an engine module's own mechanics lives in `game/tests/unit/logic/` and may import `game.logic`
  directly. Session and server tests that stage mid-round state do it through the staging helpers
  (`game/tests/helpers/builders.py`, `game/tests/unit/logic/helpers.py`), never by importing `game.logic`.
* The seam suite (`game/tests/seam/`) imports only `game.engine` and helpers that do the same, which an
  import-linter contract enforces. It stages games through setup walls and played actions alone and covers
  decisions, defaults, refusals and partial call answers.
* The facade exports the seam and nothing else: the service protocol, its implementation and the game handle;
  the setup inputs; actions, decisions, refusals, the awaiting type and the seat view; the trusted state type;
  events and results with the domain enums and values on their fields; the RNG, wall, shanten and tile
  primitives; the constants of the one rules preset. A name joins `__all__` only when it belongs to one of those,
  and leaves it once nothing outside the engine imports it.

## Seam invariants

* The engine owns rules, calculations and state transitions only. It plays one fixed preset and takes no settings,
  and it holds no names, game id, bot flags, decision ids, timers, pauses or wire codes. It emits no prompt
  messages: an open call's pending answers are rule state, and what a seat may do is read from its `decision`.
* The engine never learns who answers a seat: a person, an AI player and a timeout all answer through the same
  `act`, one answer of one seat per call, and each call returns only that answer's events. What the game waits
  for next is a separate read: `get_awaiting` says dealt, a seat's turn, an open call's pending seats, round over or
  game over, naming every awaited seat, AI players' included. Which wait is new, its decision ids, its timers and
  when a timeout plays the seat's `default_action` are the caller's.
* The engine holds no pause: `new_game` and `deal_next_round` stop after the deal (`Dealt`), and a round end that
  does not end the game stops on `RoundOver`, neither awaiting a seat; the caller moves on with `begin_round` (the
  dealer's first draw) and `deal_next_round` when it is ready, and until then the round plays no action.
* The seat is a player's only identity: every call takes a seat. The seed, who sits where and under what name are
  the caller's; `new_game` takes the seed and plays the same game for the same seed and inputs.
* Events are facts with their own routing target, a broadcast or one seat. A draw is a private draw to its seat,
  with the live wall left, plus a notice to each other seat that names only the drawer. Events, results and the
  view carry tile ids, full point values and domain melds; the wire encodings are messaging's and the wire's, and
  so is the replay's rules envelope, which always names the preset with no overrides.
* `get_awaiting`, `legal_actions`, `default_action`, `decision` and `view` are read-only: calling them changes
  nothing, in any phase.
* A refusal changes nothing: `act`, `begin_round` and `deal_next_round` return a `Refusal` for a player's input or
  a call in the wrong phase and leave the game as it was; what the refusal leads to is the caller's.
* A seat's `default_action` is never a win or a call, so a timeout can always play it.
* `view(seat)` shows the seat its own hand, furiten and decision, the public table, the round's header and the
  game's history, never another seat's concealed tiles, offers or pending answers. Outside code reads the game only
  through the view, `get_awaiting` and the decision calls; the runtime's state is the trusted full state for tests
  and equality checks only: never saved, restored or read field by field outside the engine.
