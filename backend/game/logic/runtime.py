from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from game.logic.furiten_tracker import FuritenTracker

if TYPE_CHECKING:
    from game.logic.ai_player_controller import AIPlayerController
    from game.logic.round_advance import PendingRoundAdvance
    from game.logic.state import MahjongGameState


@dataclass(eq=False)
class GameRuntime:
    """
    Everything the engine holds for one game: its frozen state and the side state beside it.

    ai knows which seats AI players hold (replacement and restoration change it); furiten remembers each seat's last
    reported furiten; pending_confirm is the round end still waiting for human confirmations, None otherwise.
    """

    game_id: str
    state: MahjongGameState
    ai: AIPlayerController
    furiten: FuritenTracker = field(default_factory=FuritenTracker)
    pending_confirm: PendingRoundAdvance | None = None
