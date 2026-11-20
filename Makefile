export PATH := $(shell mise bin-paths node go golangci-lint 2>/dev/null | tr '\n' ':')$(PATH)

BE_RUN := uv run --project backend

DOCFORMATTER_PATHS := conftest.py game lobby scripts shared

FRONTEND_APPS := lobby game_v2

.PHONY: test coverage-branches run-local-server run-debug lint format typecheck install-frontend typecheck-frontend format-frontend lint-frontend test-frontend format-go lint-go test-go vuln-go run-all-checks run-games run-tournament deadcode generate-replays generate-fixtures fixtures-check profile profile-games measure-wall run-game-v2-docker stop-game-v2-docker

test:
	cd backend && uv run pytest -v --cov --cov-report=
	cd backend && uv run coverage report --include='game/logic/*,game/wire/*' --fail-under=100

coverage-branches:
	cd backend && uv run pytest --cov --cov-branch --cov-report=term-missing:skip-covered

run-local-server:
	@bash ./bin/run-local-server.sh

lint:
	cd backend && uv run docformatter --check --diff $(DOCFORMATTER_PATHS)
	cd backend && uv run ruff format --check . ../bin
	cd backend && uv run ruff check . ../bin
	cd backend && uv run lint-imports
	$(BE_RUN) python bin/check_i18n.py

format:
	cd backend && (uv run docformatter --in-place $(DOCFORMATTER_PATHS) ; rc=$$?; [ $$rc -eq 0 ] || [ $$rc -eq 3 ])
	cd backend && uv run ruff check --fix . ../bin
	cd backend && uv run ruff format . ../bin

typecheck:
	cd backend && uv run ty check

install-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm ci) || exit 1; done
	cd frontend/game_v2 && npx playwright install chromium webkit

typecheck-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run typecheck) || exit 1; done

format-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run fmt) || exit 1; done

lint-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run lint) || exit 1; done

test-frontend:
	for app in $(FRONTEND_APPS); do (cd frontend/$$app && npm run test) || exit 1; done

format-go:
	cd backend/game_v2 && golangci-lint fmt

lint-go:
	cd backend/game_v2 && go mod tidy -diff && golangci-lint run

test-go:
	cd backend/game_v2 && go test -race -shuffle=on -timeout=2m -coverprofile=coverage.out -coverpkg=./engine/...,./internal/wire/... ./...
	$(BE_RUN) python bin/check_go_coverage.py backend/game_v2/coverage.out

vuln-go:
	cd backend/game_v2 && go run golang.org/x/vuln/cmd/govulncheck@v1.10.0 ./...

run-debug:
	$(BE_RUN) python backend/debug.py

run-all-checks:
	@bash ./bin/run-all-checks.sh|| true

deadcode:
	$(BE_RUN) python bin/check-dead-code.py backend

generate-replays:
	$(BE_RUN) python -m game.replay.external.tenhou

generate-fixtures:
	cd backend/game_v2 && go run ./cmd/fixtures

fixtures-check:
	cd backend/game_v2 && go run ./cmd/fixtures -check

profile:
ifeq ($(SERVER),go)
	@bash ./bin/profile-go-replay.sh
else
	$(BE_RUN) python bin/profile_replay.py
endif

run-games:
	@TABLES=$(TABLES) MODE=$(MODE) NET=$(NET) SERVER=$(SERVER) bash ./bin/run-bots-games.sh $(GAMES)

run-tournament:
	@bash ./bin/run-tournament.sh

profile-games:
	@PROFILE=1 TABLES=12 MODE= SERVER=$(SERVER) bash ./bin/run-bots-games.sh 48

measure-wall:
ifeq ($(SERVER),go)
	@bin_dir=$$(mktemp -d) && trap 'rm -rf "$$bin_dir"' EXIT && \
		go build -C backend/game_v2 -o "$$bin_dir/measurewall" ./cmd/measurewall && \
		cd backend && "$$bin_dir/measurewall" $(MEASURE_ARGS)
else
	cd backend && uv run python -m scripts.measure_wall $(MEASURE_ARGS)
endif

GAME_V2_COMPOSE = set -a && . ./.env.local && set +a && \
	GO_VERSION=$$(sed -n 's/^go = "\(.*\)"$$/\1/p' mise.toml) \
	APP_VERSION=$$(sed -n 's/^version = "\(.*\)"$$/\1/p' backend/pyproject.toml) \
	GIT_COMMIT=$$(git rev-parse --short=7 HEAD) \
	GAME_V2_UID=$$(id -u) GAME_V2_GID=$$(id -g) \
	docker compose -f backend/game_v2/docker-compose.local.yml

run-game-v2-docker:
	mkdir -p backend/data/game-v2-replays
	$(GAME_V2_COMPOSE) up --build --detach --wait

stop-game-v2-docker:
	$(GAME_V2_COMPOSE) down

-include Makefile.local
