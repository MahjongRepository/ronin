import asyncio
from types import SimpleNamespace

import pytest

from game.logic import mahjong_service as mahjong_service_module
from game.logic.mahjong_service import MahjongGameService
from game.session import timer as timer_module
from game.tests.helpers.session import make_session_manager

from .helpers import ENGINE_SEED


@pytest.fixture
def manager():
    return make_session_manager()


@pytest.fixture
def seeded_engine(monkeypatch):
    monkeypatch.setattr(mahjong_service_module, "generate_seed", lambda: ENGINE_SEED)
    return MahjongGameService()


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class HeldSleep:
    def __init__(self) -> None:
        self.durations: list[float] = []
        self._releases: list[asyncio.Event] = []

    async def sleep(self, seconds: float) -> None:
        release = asyncio.Event()
        self.durations.append(seconds)
        self._releases.append(release)
        await release.wait()

    def wake_all(self) -> None:
        for release in self._releases:
            release.set()

    async def release_all(self) -> None:
        self.wake_all()
        await asyncio.sleep(0)
        await asyncio.sleep(0)


@pytest.fixture
def fake_clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(timer_module, "time", SimpleNamespace(monotonic=clock.monotonic))
    return clock


@pytest.fixture
def held_sleep(monkeypatch):
    held = HeldSleep()
    monkeypatch.setattr(timer_module, "asyncio", SimpleNamespace(create_task=asyncio.create_task, sleep=held.sleep))
    return held
