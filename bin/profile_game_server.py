from __future__ import annotations

import signal
import sys
from pathlib import Path
from types import FrameType

from sampled_profile import CpuSampler
from uvicorn.main import main as uvicorn_main


def _exit_on_signal(signum: int, _frame: FrameType | None) -> None:
    raise SystemExit(128 + signum)


def main() -> None:
    """Run uvicorn with the arguments after the output path, writing its sampled profile there on exit.

    uvicorn re-raises the SIGTERM or SIGINT that stopped it once it has shut down, under the handler
    that was installed before it started; raising SystemExit there lets the samples be written.
    """
    output = Path(sys.argv[1])
    signal.signal(signal.SIGTERM, _exit_on_signal)
    signal.signal(signal.SIGINT, _exit_on_signal)
    sampler = CpuSampler()
    sampler.start()
    try:
        uvicorn_main(sys.argv[2:])
    finally:
        sampler.stop()
        sampler.write(output)


if __name__ == "__main__":
    main()
