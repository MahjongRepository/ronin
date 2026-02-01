export PATH := $(HOME)/.bun/bin:$(PATH)

.PHONY: test test-lobby test-game run-lobby run-game run-client run-all run-debug lint format typecheck typecheck-client lint-client format-client check-agent process-logs

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

run-client:
	cd client && bun run dev

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

typecheck-client:
	cd client && bun run typecheck

lint-client:
	cd client && bun run lint

format-client:
	cd client && bun run fmt
	cd client && bun run lint:fix

run-debug:
	PYTHONPATH=src uv run python src/debug.py

check-agent:
	@bash ./bin/check-agent.sh || true

process-logs:
	@bash ./bin/process-logs.sh
