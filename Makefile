export PATH := $(shell mise where node 2>/dev/null)/bin:$(PATH)

BE_RUN := uv run --project backend

DOCFORMATTER_PATHS := conftest.py game lobby scripts shared

FRONTEND_APPS := lobby game

.PHONY: test coverage-branches run-local-server run-debug lint format typecheck install-frontend typecheck-frontend format-frontend lint-frontend test-frontend run-all-checks run-games deadcode generate-replays generate-replay-fixtures replay-fixtures-check profile profile-games measure-wall

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
	$(BE_RUN) python bin/check_i18n.py

format:
	cd backend && (uv run docformatter --in-place $(DOCFORMATTER_PATHS) ; rc=$$?; [ $$rc -eq 0 ] || [ $$rc -eq 3 ])
	cd backend && uv run ruff check --fix
	cd backend && uv run ruff format

typecheck:
	cd backend && uv run ty check

install-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm ci) || exit 1; done

typecheck-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run typecheck) || exit 1; done

format-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run fmt) || exit 1; done

lint-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run lint) || exit 1; done

test-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run test) || exit 1; done

run-debug:
	$(BE_RUN) python backend/debug.py

run-all-checks:
	@bash ./bin/run-all-checks.sh|| true

deadcode:
	$(BE_RUN) python bin/check-dead-code.py backend

generate-replays:
	$(BE_RUN) python -m game.replay.external.tenhou

generate-replay-fixtures:
	cd backend && uv run python -m scripts.generate_replay_fixtures

replay-fixtures-check:
	cd backend && uv run python -m scripts.generate_replay_fixtures --check

profile:
	$(BE_RUN) python bin/profile_replay.py

run-games:
	@TABLES=$(TABLES) bash ./bin/run-bots-games.sh $(GAMES)

profile-games:
	@PROFILE=1 TABLES=12 bash ./bin/run-bots-games.sh 48

measure-wall:
	cd backend && uv run python -m scripts.measure_wall $(MEASURE_ARGS)
