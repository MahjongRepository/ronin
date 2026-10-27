export PATH := $(HOME)/.bun/bin:$(PATH)

BE_RUN := uv run --project backend

DOCFORMATTER_PATHS := conftest.py game lobby scripts shared

FRONTEND_APPS := lobby game

.PHONY: test coverage-branches run-local-server run-debug lint format typecheck install-frontend typecheck-frontend format-frontend lint-frontend test-frontend run-all-checks run-games deadcode generate-replays profile

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

install-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && bun install) || exit 1; done

typecheck-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && bun run typecheck) || exit 1; done

format-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && bun run fmt) || exit 1; done

lint-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && bun run lint) || exit 1; done

test-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && bun run test) || exit 1; done

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

run-games:
	@bash ./bin/run-bots-games.sh $(GAMES)
