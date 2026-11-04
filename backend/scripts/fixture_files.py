from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


@dataclass(frozen=True)
class FixtureDir:
    """
    A directory of generated fixtures the repository commits: every file with the suffix in it is one a generator
    produces, by name.
    """

    path: Path
    suffix: str

    def find_drift(self, generated: Mapping[str, str | bytes]) -> list[str]:
        """
        Name each committed fixture that differs from its generated contents, is missing, or has no scenario.
        """
        committed = {path.name for path in self.path.glob(f"*{self.suffix}")}
        problems = [f"orphaned: {name} (no scenario produces it)" for name in sorted(committed - generated.keys())]
        for name, text in generated.items():
            if name not in committed:
                problems.append(f"missing: {name}")
                continue

            expected = text.encode("utf-8") if isinstance(text, str) else text
            if (self.path / name).read_bytes() != expected:
                problems.append(f"stale: {name}")

        return problems

    def write(self, generated: Mapping[str, str | bytes]) -> None:
        """
        Write every generated fixture and delete the committed ones no scenario produces.
        """
        self.path.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.path.glob(f"*{self.suffix}")):
            if path.name not in generated:
                path.unlink()
                print(f"removed {path.name}")

        for name, text in generated.items():
            content = text.encode("utf-8") if isinstance(text, str) else text
            (self.path / name).write_bytes(content)
