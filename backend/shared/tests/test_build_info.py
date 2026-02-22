"""Tests for shared.build_info module."""

import importlib
import os
import subprocess
from unittest.mock import patch

import shared.build_info as build_info_module


class TestGitShortSha:
    def test_returns_short_sha_from_git(self):
        result = build_info_module._git_short_sha()
        # In a git repo, should return a hex string (7+ chars)
        assert len(result) >= 7
        assert all(c in "0123456789abcdef" for c in result)

    def test_returns_dev_when_git_not_found(self):
        with patch("subprocess.check_output", side_effect=FileNotFoundError):
            assert build_info_module._git_short_sha() == "dev"

    def test_returns_dev_when_git_fails(self):
        with patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            assert build_info_module._git_short_sha() == "dev"


class TestModuleLevelConstants:
    def test_app_version_reads_from_env(self):
        with patch.dict("os.environ", {"APP_VERSION": "1.2.3"}):
            importlib.reload(build_info_module)
            assert build_info_module.APP_VERSION == "1.2.3"
        # Restore
        importlib.reload(build_info_module)

    def test_git_commit_reads_from_env(self):
        with patch.dict("os.environ", {"GIT_COMMIT": "abc1234"}):
            importlib.reload(build_info_module)
            assert build_info_module.GIT_COMMIT == "abc1234"
        # Restore
        importlib.reload(build_info_module)

    def test_git_commit_falls_back_to_git(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GIT_COMMIT", None)
            importlib.reload(build_info_module)
            # Should be a real git SHA in this repo
            assert build_info_module.GIT_COMMIT != "dev"
            assert len(build_info_module.GIT_COMMIT) >= 7
        # Restore
        importlib.reload(build_info_module)
