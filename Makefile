.PHONY: test test-lobby test-game run-lobby run-game run-all lint format typecheck check-agent

test:
	uv run pytest -v

test-lobby:
	uv run pytest -v src/lobby/tests

test-game:
	uv run pytest -v src/game/tests

run-lobby:
	uv run uvicorn lobby.server.app:app --reload --host 0.0.0.0 --port 8000

run-game:
	uv run uvicorn game.server.app:app --reload --host 0.0.0.0 --port 8001

run-all:
	@bash ./bin/run_all.sh

lint:
	uv run ruff format --check src
	uv run ruff check src

format:
	uv run ruff check --select I --fix src
	uv run ruff format src

typecheck:
	uv run ty check src

check-agent:
	@bash ./bin/check-agent.sh || true
