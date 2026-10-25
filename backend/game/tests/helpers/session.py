from typing import TYPE_CHECKING

from game.session.manager import SessionManager
from game.session.replay_collector import ReplayCollector
from game.session.timer import TimerConfig
from game.tests.mocks import FakeGameRepository, FakeReplayStorage, MockGameService

if TYPE_CHECKING:
    from game.logic.service import GameService
    from shared.dal.game_repository import GameRepository
    from shared.storage import ReplayStorage


def make_session_manager(
    engine: GameService | None = None,
    *,
    repository: GameRepository | None = None,
    storage: ReplayStorage | None = None,
    timer_config: TimerConfig | None = None,
) -> SessionManager:
    return SessionManager(
        engine if engine is not None else MockGameService(),
        game_repository=repository if repository is not None else FakeGameRepository(),
        replay_collector=ReplayCollector(storage if storage is not None else FakeReplayStorage()),
        timer_config=timer_config if timer_config is not None else TimerConfig(game_start_pause_seconds=0),
    )
