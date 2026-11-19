"""
Check that a Go cover profile leaves no statement block under engine/ or internal/wire/ uncovered.

The profile lists a block once per test binary, so a block is covered when any of its lines counts
above zero. A block of no statement, the empty body of a sum type's marker method, holds nothing
to cover and is skipped. Each uncovered block prints one line; the exit status is 1 when there is
any, or when the profile holds no block of one of the gated directories at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

GATED_DIRS = ("/game_v2/engine/", "/game_v2/internal/wire/")
MODE_PREFIX = "mode:"


def find_uncovered_blocks(profile: str) -> list[str]:
    """
    Return the gated blocks no test binary executed, sorted.

    Raise ValueError when the profile holds no block of one of the gated directories.
    """
    covered_by_block: dict[str, bool] = {}
    for line in profile.splitlines():
        if not line or line.startswith(MODE_PREFIX):
            continue

        block, statements, count = line.rsplit(" ", 2)
        if int(statements) == 0:
            continue

        covered_by_block[block] = covered_by_block.get(block, False) or int(count) > 0

    for gated_dir in GATED_DIRS:
        if not any(gated_dir in block for block in covered_by_block):
            raise ValueError(f"the cover profile holds no block under {gated_dir.removeprefix('/game_v2/')}")

    gated_blocks = {
        block: covered
        for block, covered in covered_by_block.items()
        if any(gated_dir in block for gated_dir in GATED_DIRS)
    }
    return sorted(block for block, covered in gated_blocks.items() if not covered)


def main(arguments: list[str]) -> int:
    """
    Print the uncovered gated blocks of the profile named by the only argument.
    """
    if len(arguments) != 1:
        sys.stderr.write("usage: check_go_coverage.py <profile>\n")
        return 1

    try:
        uncovered = find_uncovered_blocks(Path(arguments[0]).read_text())
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 1

    sys.stderr.writelines(f"uncovered: {block}\n" for block in uncovered)
    return 1 if uncovered else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
