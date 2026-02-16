export PATH := $(HOME)/.bun/bin:$(PATH)

.PHONY: test run-local-server run-debug lint format typecheck typecheck-client format-client lint-client run-all-checks run-games deadcode

test:
	uv run pytest -v

run-local-server:
	@bash ./bin/run-local-server.sh

lint:
	uv run ruff format --check src
	uv run ruff check src

format:
	uv run ruff check --fix src
	uv run ruff format src

typecheck:
	uv run ty check src

typecheck-client:
	cd client && bun run typecheck

format-client:
	cd client && bun run fmt

lint-client:
	cd client && bun run lint

run-debug:
	PYTHONPATH=src uv run python src/debug.py

run-all-checks:
	@bash ./bin/run-all-checks.sh|| true

deadcode:
	uv run python bin/check-dead-code.py src
