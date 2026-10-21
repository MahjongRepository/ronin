# Backend (Python / Starlette)

Before working in `game/` or `lobby/`, read that directory's `AGENTS.md` and the architecture
documents it names.

## Tooling

* One uv project at the repo root; run everything from there. `pyproject.toml` installs
  `backend/game`, `backend/lobby` and `backend/shared` as packages, so imports are rooted at
  `backend/` (`from game.logic.state import ...`). `backend/conftest.py` loads `.env.tests` and
  routes structlog through stdlib logging so `caplog` sees it.
* `make lint` (ruff format check + ruff), `make typecheck` (`ty check backend`), `make test`.

## Conventions

* Game state and domain events are frozen Pydantic models (`game/logic/state.py`); the other
  existing Pydantic families (`ServiceEvent`, the incoming messages in `game/messaging/types.py`) are
  extended in kind, keeping each family's mutability. Elsewhere — lobby room and matchmaking state,
  event routing targets — follow the shared rule: a `@dataclass` unless the data needs validation.
* Docstrings are imperative ("Calculate...", not "Calculates..."): a one-line summary, then a blank
  line and parameter/return detail only when the function is not obvious.

## Tests

* Build test data with the helpers in `game/tests/helpers/` and the suite's `conftest.py` fixtures,
  not raw tile ids or magic strings.
