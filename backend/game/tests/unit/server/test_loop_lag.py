import asyncio

import pytest

from game.server.loop_lag import LoopLagProbe


class FakeLoop:
    def __init__(self, lateness_per_wake: list[float]) -> None:
        self.now = 0.0
        self._lateness_per_wake = list(lateness_per_wake)

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        if not self._lateness_per_wake:
            raise asyncio.CancelledError

        self.now += seconds + self._lateness_per_wake.pop(0)


async def _run_probe(lateness_per_wake: list[float]) -> tuple[LoopLagProbe, FakeLoop]:
    fake_loop = FakeLoop(lateness_per_wake)
    probe = LoopLagProbe(clock=fake_loop.clock, sleep=fake_loop.sleep)
    with pytest.raises(asyncio.CancelledError):
        await probe.run()

    return probe, fake_loop


def test_loop_lag_probe__when_never_woken__should_report_none():
    assert LoopLagProbe().max_ms is None


async def test_loop_lag_probe__when_woken_late__should_report_worst_lateness_in_ms():
    probe, _ = await _run_probe([0.0, 0.25, 0.125])

    assert probe.max_ms == 250.0


async def test_loop_lag_probe__when_worst_observation_older_than_a_minute__should_drop_it():
    probe, fake_loop = await _run_probe([0.5, 0.0, 0.125])

    fake_loop.now += 58.0
    assert probe.max_ms == 125.0
    fake_loop.now += 3.0
    assert probe.max_ms is None
