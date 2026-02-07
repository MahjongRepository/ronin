import pytest

from game.session.manager import SessionManager
from game.tests.mocks import MockGameService


@pytest.fixture
def manager():
    game_service = MockGameService()
    return SessionManager(game_service)
