"""
Replay adapter for deterministic game replay through MahjongGameService.

Dependency direction: replay imports from game.logic and game.messaging.
Game logic modules never import from replay.
"""

from game.replay.loader import (
    ReplayLoadError,
    load_replay_from_file,
    load_replay_from_string,
)
from game.replay.models import (
    REPLAY_VERSION,
    ReplayError,
    ReplayInput,
    ReplayInputAfterGameEndError,
    ReplayInputEvent,
    ReplayInvariantError,
    ReplayStartupError,
    ReplayStep,
    ReplayStepLimitError,
    ReplayTrace,
)
from game.replay.runner import (
    ReplayServiceProtocol,
    run_replay,
    run_replay_async,
)

__all__ = [
    "REPLAY_VERSION",
    "ReplayError",
    "ReplayInput",
    "ReplayInputAfterGameEndError",
    "ReplayInputEvent",
    "ReplayInvariantError",
    "ReplayLoadError",
    "ReplayServiceProtocol",
    "ReplayStartupError",
    "ReplayStep",
    "ReplayStepLimitError",
    "ReplayTrace",
    "load_replay_from_file",
    "load_replay_from_string",
    "run_replay",
    "run_replay_async",
]
