SSH_KEY ?= $(HOME)/.ssh/id_ed25519
TARGET ?= prod
ENV_FILE = spot-env.$(TARGET).yml
SPOT = spot -v -p spot.yml -i $(ENV_FILE) -E $(ENV_FILE) --key=$(SSH_KEY)

ifeq (,$(wildcard $(ENV_FILE)))
$(error $(ENV_FILE) not found: copy spot-env.example.yml and set the host, user and domain (README.md))
endif

.PHONY: spot-run spot-bootstrap spot-provision spot-monitoring spot-deploy spot-update spot-stop spot-restart spot-down spot-status spot-check-logs-errors spot-metrics spot-metrics-sql spot-backup spot-restore spot-backup-list spot-download-backup

spot-run:
ifndef TASK
	$(error TASK is required. Usage: make spot-run TASK=<task>)
endif
	$(SPOT) -t $(TARGET) -n $(TASK)

# Bootstrap: base packages, dirs, env templates
spot-bootstrap:
	$(SPOT) -t $(TARGET) -n bootstrap

# Provision: SSH hardening, Docker, firewall, backups, journald
spot-provision:
	$(SPOT) -t $(TARGET) -n setup-ssh
	$(SPOT) -t $(TARGET) -n setup-docker
	$(SPOT) -t $(TARGET) -n setup-firewall
	$(SPOT) -t $(TARGET) -n setup-restic
	$(SPOT) -t $(TARGET) -n setup-monitoring
	$(SPOT) -t $(TARGET) -n setup-journald

spot-monitoring:
	$(SPOT) -t $(TARGET) -n setup-monitoring

# Deploy: pull image, restart services
spot-deploy:
	$(SPOT) -t $(TARGET) -n deploy

# Update: pull latest images and restart changed services
spot-update:
	$(SPOT) -t $(TARGET) -n update

# Stop: stop all services (containers preserved)
spot-stop:
	$(SPOT) -t $(TARGET) -n stop

# Restart: restart all services
spot-restart:
	$(SPOT) -t $(TARGET) -n restart

# Down: stop and remove all containers
spot-down:
	$(SPOT) -t $(TARGET) -n down

# Status: show service status
spot-status:
	$(SPOT) -t $(TARGET) -n status

# Errors: show errors from logs (app-level errors, exceptions, tracebacks)
#   make spot-check-logs-errors                          # last 24 hours (default)
#   make spot-check-logs-errors SINCE="2 hours ago"      # last 2 hours
#   make spot-check-logs-errors SINCE="2026-03-01"       # since a specific date
LOGS_FILE := /tmp/ronin-errors.log
spot-check-logs-errors:
ifdef SINCE
	$(SPOT) -t $(TARGET) -n check-logs-errors -e SINCE:"$(SINCE)" | tee $(LOGS_FILE) | grep '> '
else
	$(SPOT) -t $(TARGET) -n check-logs-errors | tee $(LOGS_FILE) | grep '> '
endif
	@grep '^\[.*\] *> ' $(LOGS_FILE) | sed 's/^\[.*\] *> *//' | grep -v '^\(/bin/sh\|Checking ronin\|^$$\)' > $(LOGS_FILE).tmp && mv $(LOGS_FILE).tmp $(LOGS_FILE)
	@echo ""
	cat $(LOGS_FILE)
	@echo "Saved to $(LOGS_FILE)"

RANGE ?= 24h
SPOT_OUTPUT_LINES = sed -n '/^\[[^]]*\] *> \/bin\/sh/d; s/^\[[^]]*\] *> //p'
UNSAFE_SQL = $(if $(filter .%,$(firstword $(value SQL)))$(findstring $$,$(value SQL))$(findstring `,$(value SQL))$(findstring ",$(value SQL)),unsafe)

spot-metrics spot-metrics-sql: SHELL := /bin/bash
spot-metrics spot-metrics-sql: .SHELLFLAGS := -o pipefail -c

spot-metrics:
ifneq ($(value RANGE),$(filter 1h 24h 7d 30d 90d,$(value RANGE)))
	$(error RANGE must be one of 1h, 24h, 7d, 30d, 90d)
endif
	@$(SPOT) -t $(TARGET) -n metrics-report -e RANGE:"$(RANGE)" | $(SPOT_OUTPUT_LINES)

spot-metrics-sql:
ifndef SQL
	$(error SQL is required. Usage: make spot-metrics-sql SQL="SELECT ...")
endif
ifneq (,$(UNSAFE_SQL))
	$(error SQL must not start with a dot-command or contain a backtick, $$ or ")
endif
	@$(SPOT) -t $(TARGET) -n metrics-sql -e SQL:"$(SQL)" | $(SPOT_OUTPUT_LINES)

# Backup: run a manual backup
spot-backup:
	$(SPOT) -t $(TARGET) -n backup

# Restore: restore from a snapshot (use SNAPSHOT=<id> for a specific snapshot)
spot-restore:
ifdef SNAPSHOT
	$(SPOT) -t $(TARGET) -n restore -e SNAPSHOT:$(SNAPSHOT)
else
	$(SPOT) -t $(TARGET) -n restore
endif

# Download backup from server and restore locally (replaces local DB and replays)
spot-download-backup:
	$(SPOT) -t $(TARGET) -n backup-download
	@bash scripts/restore-local.sh

# List backup snapshots
spot-backup-list:
	$(SPOT) -t $(TARGET) -n backup-list
