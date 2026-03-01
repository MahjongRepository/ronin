# Spot SSH: auto-detect 1Password agent, fall back to system agent.
# Override with SSH_KEY=~/.ssh/id_rsa for key-based auth.
ONEPASS_SOCK := $(HOME)/.1password/agent.sock
ifdef SSH_KEY
  SPOT_SSH := --key=$(SSH_KEY)
else ifneq (,$(wildcard $(ONEPASS_SOCK)))
  SPOT_SSH_ENV := SSH_AUTH_SOCK=$(ONEPASS_SOCK)
  SPOT_SSH := --ssh-agent
else
  SPOT_SSH := --ssh-agent
endif
TARGET ?= dev
SPOT = $(SPOT_SSH_ENV) spot -v -p spot.yml -E spot-env.$(TARGET).yml $(SPOT_SSH)

.PHONY: spot-run spot-bootstrap spot-provision spot-deploy spot-update spot-stop spot-restart spot-down spot-status spot-check-logs-errors spot-backup spot-restore spot-backup-list spot-download-backup

# Run arbitrary spot task: make spot-run TASK=<task> TARGET=dev
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
	$(SPOT) -t $(TARGET) -n setup-journald

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
