from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from game.logic.furiten_tracker import FuritenTracker
from game.logic.invariants import verify_tile_ownership

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

    The state is replaced only through commit(), which checks the tile ownership invariant first, so a corrupted state
    never becomes the game's state: the raise lands in the server-fault path and the game ends. The initial state is
    checked by start_game's first commit, before any event leaves the engine.
    """

    game_id: str
    state: MahjongGameState
    ai: AIPlayerController
    furiten: FuritenTracker = field(default_factory=FuritenTracker)
    pending_confirm: PendingRoundAdvance | None = None

    def commit(self, state: MahjongGameState) -> None:
        """
        Make state the game's state after verifying it owns every tile exactly once.
        """
        verify_tile_ownership(state)
        self.state = state
