import subprocess

from pydantic_settings import BaseSettings


class BuildInfo(BaseSettings):
    model_config = {"env_prefix": ""}

    app_version: str = "dev"
    git_commit: str = ""


def _git_short_sha() -> str:
    """
    Read short SHA from git for local development.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except FileNotFoundError, subprocess.CalledProcessError:
        return "dev"


_build_info = BuildInfo()

APP_VERSION: str = _build_info.app_version
GIT_COMMIT: str = _build_info.git_commit or _git_short_sha()
