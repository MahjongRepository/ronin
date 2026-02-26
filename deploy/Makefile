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

.PHONY: spot-run spot-setup spot-deploy

# Run arbitrary spot task: make spot-run TASK=setup-firewall TARGET=dev
spot-run:
	$(SPOT) -t $(TARGET) -n $(TASK)

# One-time server provisioning (Docker + Traefik): make spot-setup TARGET=dev
spot-setup:
	$(SPOT) -t $(TARGET) -n setup-ssh
	$(SPOT) -t $(TARGET) -n setup-docker
	$(SPOT) -t $(TARGET) -n setup-firewall
	$(SPOT) -t $(TARGET) -n setup-app

# Deploy app: make spot-deploy TARGET=dev
spot-deploy:
	$(SPOT) -t $(TARGET) -n deploy
