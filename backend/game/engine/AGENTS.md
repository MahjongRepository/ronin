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
  directly. A seam test (`game/tests/seam/`) imports only `game.engine` and helpers that do the same, and stages
  a game only through setup inputs and played actions, so it can run against another engine.
* The facade exports the seam and nothing else: the service protocol, its implementation and the game handle;
  actions, decisions, refusals, the awaiting type and the seat view; events and results with the domain enums and
  values on their fields; the RNG, wall, shanten and tile primitives; the constants of the one rules preset. A name
  joins `__all__` only when it belongs to one of those, and leaves it once nothing outside the engine imports it.

## Seam invariants

* The engine owns rules, calculations and state transitions only. It plays one fixed preset and takes no settings,
  and it holds no names, game id, bot flags, decision ids, timers, pauses, prompts or wire codes.
* The engine never learns who answers a seat: a person, an AI player and a timeout all answer through the same
  `act`, one answer of one seat per call. `get_awaiting` names every awaited seat, AI players' included.
* `get_awaiting`, `legal_actions`, `default_action`, `decision` and `view` are read-only: calling them changes
  nothing, in any phase.
* A refusal changes nothing: `act`, `begin_round` and `deal_next_round` return a `Refusal` for a player's input or
  a call in the wrong phase and leave the game as it was; what the refusal leads to is the caller's.
* A seat's `default_action` is never a win or a call, so a timeout can always play it.
* `view(seat)` never shows another seat's concealed tiles, offers or pending answers. The runtime's state is the
  trusted full state for tests and equality checks only: never saved, restored or read field by field outside the
  engine.
