"""
Replay adapter for deterministic game replay through MahjongGameService.

Dependency direction: replay imports from game.logic and game.messaging.
Game logic modules never import from replay.
"""

from game.replay.models import (
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
    "ReplayError",
    "ReplayInput",
    "ReplayInputAfterGameEndError",
    "ReplayInputEvent",
    "ReplayInvariantError",
    "ReplayServiceProtocol",
    "ReplayStartupError",
    "ReplayStep",
    "ReplayStepLimitError",
    "ReplayTrace",
    "run_replay",
    "run_replay_async",
]
