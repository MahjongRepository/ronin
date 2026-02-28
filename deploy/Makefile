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
SPOT = $(SPOT_SSH_ENV) spot -p spot.yml -E spot-env.$(TARGET).yml $(SPOT_SSH)

.PHONY: spot-run spot-bootstrap spot-provision spot-deploy spot-backup spot-restore spot-backup-list spot-download-backup

# Run arbitrary spot task: make spot-run TASK=<task> TARGET=dev
spot-run:
	$(SPOT) -t $(TARGET) -n $(TASK)

# Bootstrap: base packages, dirs, env templates
spot-bootstrap:
	$(SPOT) -t $(TARGET) -n bootstrap

# Provision: SSH hardening, Docker, firewall, backups
spot-provision:
	$(SPOT) -t $(TARGET) -n setup-ssh
	$(SPOT) -t $(TARGET) -n setup-docker
	$(SPOT) -t $(TARGET) -n setup-firewall
	$(SPOT) -t $(TARGET) -n setup-restic

# Deploy: pull image, restart services
spot-deploy:
	$(SPOT) -t $(TARGET) -n deploy

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
