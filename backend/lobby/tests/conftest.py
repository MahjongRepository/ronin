"""Shared fixtures for lobby tests."""

import os

# Auth settings require AUTH_GAME_TICKET_SECRET. Set a test default
# before any AuthSettings is instantiated.
os.environ.setdefault("AUTH_GAME_TICKET_SECRET", "test-secret")
