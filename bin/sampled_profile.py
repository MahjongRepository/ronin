from __future__ import annotations

import collections
import re
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import CodeType, FrameType

SAMPLE_RATE = 100
SAMPLED_FRAME = re.compile(r"(?P<name>.*) \((?P<file>.*):(?P<line>\d+)\)$")
STDLIB_DIR = f"python{sys.version_info.major}.{sys.version_info.minor}/"
IMPORT_FRAME = "_find_and_load"
LAYERS = (
    ("engine", ("game/logic/",)),
    ("replay collector", ("game/session/replay_collector",)),
    ("messaging", ("game/messaging/", "msgpack/")),
    ("session", ("game/session/",)),
    ("server and router", ("game/server/", "shared/websocket")),
    ("database", ("shared/db/",)),
    ("uvicorn and websockets", ("uvicorn/", "websockets/", "uvloop/")),
)
OTHER_LAYER = "other"

type ProfileKey = tuple[str, int, str]
type Stack = tuple[CodeType, ...]


class CpuSampler:
    """Count the main thread's Python stacks, one sample per 1/SAMPLE_RATE s of the process's CPU time.

    The kernel's ITIMER_PROF delivers SIGPROF and the interpreter runs the handler in the main thread
    at its next bytecode boundary, so a native call counts toward the Python frame it returns to.
    Nothing outside the process pauses it, so a run can never stall on the profiler.
    """

    def __init__(self) -> None:
        self.stacks: collections.Counter[Stack] = collections.Counter()

    def start(self) -> None:
        signal.signal(signal.SIGPROF, self.record)
        signal.siginterrupt(signal.SIGPROF, False)
        interval = 1 / SAMPLE_RATE
        signal.setitimer(signal.ITIMER_PROF, interval, interval)

    def stop(self) -> None:
        signal.setitimer(signal.ITIMER_PROF, 0)

    def record(self, _signum: int, frame: FrameType | None) -> None:
        codes = []
        while frame is not None:
            codes.append(frame.f_code)
            frame = frame.f_back

        self.stacks[tuple(reversed(codes))] += 1

    def write(self, output: Path) -> None:
        """Write the samples as collapsed stacks, root first, one `stack count` line each."""
        lines = [f"{';'.join(_format_code(code) for code in stack)} {count}\n" for stack, count in self.stacks.items()]
        output.write_text("".join(lines))


@dataclass
class SampleSummary:
    """Sample counts of a sampled profile; `excluded` holds the samples outside the measured work."""

    total: int = 0
    excluded: int = 0
    self_samples: collections.Counter[ProfileKey] = field(default_factory=collections.Counter)
    project_samples: collections.Counter[ProfileKey] = field(default_factory=collections.Counter)
    layer_samples: collections.Counter[str] = field(default_factory=collections.Counter)


def summarize_samples(sample_file: Path, *, root: str | None) -> SampleSummary:
    """Count the samples of a sampled profile that belong to the measured work.

    A sample is excluded when its stack is importing a module or, with `root`, does not pass
    through a function of that name. Each kept sample is charged to the layer of its deepest frame
    that has one, so library code counts toward the layer that called it.
    """
    summary = SampleSummary()
    for line in sample_file.read_text().splitlines():
        stack, _, count = line.rpartition(" ")
        samples = int(count)
        frames = [_parse_sampled_frame(frame) for frame in stack.split(";")]
        names = {name for _, _, name in frames}
        if IMPORT_FRAME in names or (root is not None and root not in names):
            summary.excluded += samples
            continue

        summary.total += samples
        summary.self_samples[frames[-1]] += samples
        summary.layer_samples[_layer_of(frames)] += samples
        for frame in dict.fromkeys(frames):
            if is_project_code(frame[0]):
                summary.project_samples[frame] += samples

    return summary


def print_sampled_profile(sample_file: Path, *, root: str | None, by_layer: bool) -> None:
    """Print the shares of a sampled profile's kept samples, by layer when asked, then by function."""
    summary = summarize_samples(sample_file, root=root)
    if summary.total == 0:
        print(f"No samples of the measured work in {sample_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Sampled profile: {summary.total} samples at {SAMPLE_RATE} Hz, {summary.excluded} left out: {sample_file}")
    if by_layer:
        print("Samples by layer, each charged to its deepest frame's layer:")
        _print_shares(summary.layer_samples.most_common(), summary.total)

    print("Top 20 functions by self samples, native calls charged to their Python caller:")
    _print_shares([(format_func(key), n) for key, n in summary.self_samples.most_common(20)], summary.total)
    print("Top 20 project functions by inclusive samples:")
    _print_shares([(format_func(key), n) for key, n in summary.project_samples.most_common(20)], summary.total)


def is_project_code(filename: str) -> bool:
    """Return True if filename belongs to the game server or shared code, not replay tooling, tests or libs."""
    if "game/" not in filename and "shared/" not in filename:
        return False

    return "game/replay/" not in filename and "/tests/" not in filename


def short_path(filename: str) -> str:
    """Strip absolute prefix, return a game/, shared/, site-packages or stdlib relative path."""
    for marker in ("game/", "shared/"):
        if marker in filename and "site-packages/" not in filename:
            return marker + filename.split(marker, 1)[1]

    for prefix in ("site-packages/", STDLIB_DIR):
        if prefix in filename:
            return filename.split(prefix, 1)[1]

    return filename


def format_func(key: ProfileKey) -> str:
    """Format a pstats-style function key as short_path:lineno(name)."""
    filename, lineno, func_name = key
    return f"{short_path(filename)}:{lineno}({func_name})"


def _print_shares(rows: list[tuple[str, int]], total: int) -> None:
    for label, samples in rows:
        print(f"{100 * samples / total:6.1f}%  {label}")
    print()


def _format_code(code: CodeType) -> str:
    return f"{code.co_qualname} ({code.co_filename}:{code.co_firstlineno})"


def _layer_of(frames: list[ProfileKey]) -> str:
    for filename, _, _ in reversed(frames):
        for layer, fragments in LAYERS:
            if any(fragment in filename for fragment in fragments):
                return layer

    return OTHER_LAYER


def _parse_sampled_frame(frame: str) -> ProfileKey:
    """Turn a sampled `name (file:line)` frame into a pstats-style key."""
    match = SAMPLED_FRAME.match(frame)
    if match is None:
        return ("", 0, frame)

    return (match["file"], int(match["line"]), match["name"])


def main() -> None:
    """Summarize the game server's sampled profile, the file given as the only argument."""
    print_sampled_profile(Path(sys.argv[1]), root=None, by_layer=True)


if __name__ == "__main__":
    main()
