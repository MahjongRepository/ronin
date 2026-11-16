# Engine facade

`game.engine` is the seam between the rules engine (`game.logic`) and everything that manages a game: the
session, messaging, wire, the replay tools, `scripts/` and `bin/`. Its `__init__.py` re-exports engine names
explicitly through `__all__`; it holds no wrappers, no logic of its own and no re-exported modules, and the
types stay defined in `game.logic`.

* Code outside `game.logic` imports the engine only from `game.engine`, `if TYPE_CHECKING:` imports included,
  though the lint graph leaves those out. A protected import-linter contract (`backend/pyproject.toml`) allows
  only this package, the engine-internal tests (`game/tests/unit/logic/`) and the test helpers that stage
  engine state to import `game.logic`, plus a few other tests until the seam covers what they need.
* A name outside code needs joins `__all__` here; a test of an engine module's own mechanics lives in
  `game/tests/unit/logic/` and may import `game.logic` directly.
* The surface is still shrinking toward the final seam: some exports exist only until the callers that need
  them stop doing so. Remove a name here once nothing outside the engine imports it.
