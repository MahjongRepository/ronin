export PATH := $(shell mise bin-paths node go golangci-lint 2>/dev/null | tr '\n' ':')$(PATH)

BE_RUN := uv run --project backend

DOCFORMATTER_PATHS := conftest.py lobby scripts

FRONTEND_APPS := lobby game_v2

.PHONY: test coverage-branches run-local-server run-debug lint format typecheck install-frontend typecheck-frontend format-frontend lint-frontend test-frontend format-go lint-go test-go vuln-go run-all-checks run-games run-tournament generate-fixtures fixtures-check profile profile-compare update-pgo profile-games measure-wall run-game-v2-docker stop-game-v2-docker

test:
	cd backend && uv run pytest -v --cov --cov-report=

coverage-branches:
	cd backend && uv run pytest --cov --cov-branch --cov-report=term-missing:skip-covered

run-local-server:
	@DOCKER=$(DOCKER) bash ./bin/run-local-server.sh

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
	cd backend/game_v2 && go test -race -timeout=2m ./cmd/... ./internal/...
	cd backend/game_v2 && go test -shuffle=on -timeout=2m ./...

vuln-go:
	cd backend/game_v2 && go run golang.org/x/vuln/cmd/govulncheck@v1.10.0 ./...

run-debug:
	$(BE_RUN) python backend/debug.py

run-all-checks:
	@bash ./bin/run-all-checks.sh|| true

generate-fixtures:
	cd backend/game_v2 && go run ./cmd/fixtures

fixtures-check:
	cd backend/game_v2 && go run ./cmd/fixtures -check

profile:
	@BENCH=$(BENCH) bash ./bin/profile-full-game.sh

profile-compare:
	@BENCH=$(BENCH) bash ./bin/profile-compare.sh $(BASE)

run-games:
	@TABLES=$(TABLES) MODE=$(MODE) NET=$(NET) DOCKER=$(DOCKER) bash ./bin/run-bots-games.sh $(GAMES)

run-tournament:
	@bash ./bin/run-tournament.sh

update-pgo:
	@bash ./bin/update-pgo.sh $(PGO_PROFILES)

profile-games:
	@PROFILE=1 TABLES=12 MODE= bash ./bin/run-bots-games.sh 48

measure-wall:
	@bin_dir=$$(mktemp -d) && trap 'rm -rf "$$bin_dir"' EXIT && \
		go build -C backend/game_v2 -o "$$bin_dir/measurewall" ./cmd/measurewall && \
		cd backend && "$$bin_dir/measurewall" $(MEASURE_ARGS)

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
