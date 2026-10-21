import subprocess
from unittest.mock import patch

import shared.build_info as build_info_module


class TestGitShortSha:
    def test_git_short_sha__when_in_git_repo__should_return_hex_sha(self):
        result = build_info_module._git_short_sha()
        # In a git repo, should return a hex string (7+ chars)
        assert len(result) >= 7
        assert all(c in "0123456789abcdef" for c in result)

    def test_git_short_sha__when_git_not_found__should_return_dev(self):
        with patch("subprocess.check_output", side_effect=FileNotFoundError):
            assert build_info_module._git_short_sha() == "dev"

    def test_git_short_sha__when_git_fails__should_return_dev(self):
        with patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            assert build_info_module._git_short_sha() == "dev"
