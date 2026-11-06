from __future__ import annotations

import gc
import json
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from uvicorn.main import main as uvicorn_main

from sampled_profile import CpuSampler

if TYPE_CHECKING:
    from types import FrameType


@dataclass
class GcTimer:
    """Sum the process CPU time the garbage collector spends, timed around each collection by gc.callbacks.

    A sample taken during a collection runs its handler at the "stop" callback, so it shows up under
    `GcTimer.record` and that row of the profile cross-checks this timer. Process time, not wall time,
    keeps preemption by other processes out of it.
    """

    seconds: float = 0.0
    collections: int = 0
    collection_start: float = 0.0

    def record(self, phase: str, _info: dict[str, int]) -> None:
        if phase == "start":
            self.collection_start = time.process_time()
            return

        self.seconds += time.process_time() - self.collection_start
        self.collections += 1


def _exit_on_signal(signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(128 + signum)


def write_gc_readout(path: Path, gc_timer: GcTimer, process_cpu_seconds: float) -> None:
    readout = {
        "collections": gc_timer.collections,
        "gc_seconds": gc_timer.seconds,
        "process_cpu_seconds": process_cpu_seconds,
    }
    path.write_text(json.dumps(readout, indent=2, sort_keys=True) + "\n")


def main() -> None:
    """Run uvicorn with the arguments after the output path, writing its sampled profile there on exit.

    uvicorn re-raises the SIGTERM or SIGINT that stopped it once it has shut down, under the handler
    that was installed before it started; raising SystemExit there lets the samples be written. The
    garbage collector's CPU time over the same interval goes to the output path plus `.gc.json`.
    """
    output = Path(sys.argv[1])
    signal.signal(signal.SIGTERM, _exit_on_signal)
    signal.signal(signal.SIGINT, _exit_on_signal)
    sampler = CpuSampler()
    gc_timer = GcTimer()
    gc.callbacks.append(gc_timer.record)
    cpu_start = time.process_time()
    sampler.start()
    try:
        uvicorn_main(sys.argv[2:])
    finally:
        sampler.stop()
        process_cpu_seconds = time.process_time() - cpu_start
        gc.callbacks.remove(gc_timer.record)
        sampler.write(output)
        write_gc_readout(path=Path(f"{output}.gc.json"), gc_timer=gc_timer, process_cpu_seconds=process_cpu_seconds)


if __name__ == "__main__":
    main()
