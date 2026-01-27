import pytest

from game.logic.mock import MockGameService
from game.messaging.mock import MockConnection
from game.messaging.router import MessageRouter
from game.server.app import create_app
from game.session.manager import SessionManager


@pytest.fixture
def game_service():
    return MockGameService()


@pytest.fixture
def session_manager(game_service):
    return SessionManager(game_service)


@pytest.fixture
def message_router(session_manager):
    return MessageRouter(session_manager)


@pytest.fixture
def mock_connection():
    return MockConnection()


@pytest.fixture
def app(game_service, session_manager, message_router):
    return create_app(
        game_service=game_service,
        session_manager=session_manager,
        message_router=message_router,
    )
