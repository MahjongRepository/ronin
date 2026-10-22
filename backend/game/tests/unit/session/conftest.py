import pytest

from game.logic import mahjong_service as mahjong_service_module
from game.logic.mahjong_service import MahjongGameService
from game.session import manager as manager_module
from game.session.manager import SessionManager
from game.session.models import Game
from game.session.timer import TimerConfig
from game.tests.mocks import FakeGameRepository, MockGameService

ENGINE_SEED = "a" * 192


@pytest.fixture
def manager():
    game_service = MockGameService()
    return SessionManager(game_service, game_repository=FakeGameRepository())


@pytest.fixture
def seeded_engine(monkeypatch):
    monkeypatch.setattr(mahjong_service_module, "generate_seed", lambda: ENGINE_SEED)
    return MahjongGameService()


@pytest.fixture
def short_pending_timeout(monkeypatch):
    def game_with_short_pending_timeout(**fields) -> Game:
        return Game(timer_config=TimerConfig(pending_game_timeout_seconds=0.01), **fields)

    monkeypatch.setattr(manager_module, "Game", game_with_short_pending_timeout)
