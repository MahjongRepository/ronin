export PATH := $(HOME)/.bun/bin:$(PATH)

.PHONY: test run-local-server run-debug lint format typecheck typecheck-frontend format-frontend lint-frontend run-all-checks run-games deadcode generate-replays

test:
	uv run pytest -v

run-local-server:
	@bash ./bin/run-local-server.sh

lint:
	uv run ruff format --check backend
	uv run ruff check backend

format:
	uv run ruff check --fix backend
	uv run ruff format backend

typecheck:
	uv run ty check backend

typecheck-frontend:
	cd frontend && bun run typecheck

format-frontend:
	cd frontend && bun run fmt

lint-frontend:
	cd frontend && bun run lint

run-debug:
	PYTHONPATH=backend uv run python backend/debug.py

run-all-checks:
	@bash ./bin/run-all-checks.sh|| true

deadcode:
	uv run python bin/check-dead-code.py backend

generate-replays:
	PYTHONPATH=backend uv run python -m game.replay.external.tenhou
