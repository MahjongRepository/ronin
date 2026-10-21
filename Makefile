export PATH := $(HOME)/.bun/bin:$(PATH)

BE_RUN := uv run --project backend

DOCFORMATTER_PATHS := conftest.py game lobby scripts shared

.PHONY: test coverage-branches run-local-server run-debug lint format typecheck typecheck-frontend format-frontend lint-frontend test-frontend run-all-checks run-games deadcode generate-replays profile

test:
	cd backend && uv run pytest -v --cov --cov-report=
	cd backend && uv run coverage report --include='game/logic/*,game/wire/*' --fail-under=100

coverage-branches:
	cd backend && uv run pytest --cov --cov-branch --cov-report=term-missing:skip-covered

run-local-server:
	@bash ./bin/run-local-server.sh

lint:
	cd backend && uv run docformatter --check --diff $(DOCFORMATTER_PATHS)
	cd backend && uv run ruff format --check
	cd backend && uv run ruff check
	cd backend && uv run lint-imports

format:
	cd backend && (uv run docformatter --in-place $(DOCFORMATTER_PATHS) ; rc=$$?; [ $$rc -eq 0 ] || [ $$rc -eq 3 ])
	cd backend && uv run ruff check --fix
	cd backend && uv run ruff format

typecheck:
	cd backend && uv run ty check

typecheck-frontend:
	cd frontend && bun run typecheck

format-frontend:
	cd frontend && bun run fmt

lint-frontend:
	cd frontend && bun run lint

test-frontend:
	cd frontend && bun run test

run-debug:
	$(BE_RUN) python backend/debug.py

run-all-checks:
	@bash ./bin/run-all-checks.sh|| true

deadcode:
	$(BE_RUN) python bin/check-dead-code.py backend

generate-replays:
	$(BE_RUN) python -m game.replay.external.tenhou

profile:
	$(BE_RUN) python bin/profile_replay.py
