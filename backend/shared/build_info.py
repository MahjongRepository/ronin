"""Build metadata exposed at runtime.

APP_VERSION and GIT_COMMIT are set via environment variables in CI.
For local development, GIT_COMMIT falls back to reading from git directly.
"""

import os
import subprocess


def _git_short_sha() -> str:
    """Read short SHA from git for local development."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except FileNotFoundError, subprocess.CalledProcessError:
        return "dev"


APP_VERSION: str = os.environ.get("APP_VERSION", "dev")
GIT_COMMIT: str = os.environ.get("GIT_COMMIT") or _git_short_sha()
