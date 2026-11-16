from typing import TYPE_CHECKING

from game.logic.furiten_tracker import FuritenTracker
from game.logic.invariants import verify_tile_ownership

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.logic.ai_player_controller import AIPlayerController
    from game.logic.state import MahjongGameState


class GameRuntime:
    """
    Everything the engine holds for one game: its frozen state and the side state beside it.

    ai knows which seats AI players hold (replacement and restoration change it); furiten remembers each seat's last
    reported furiten; first_draw_pending is whether the round in play is dealt and its dealer has not drawn yet; wait_id
    identifies the current wait (see `Awaiting`): the service bumps it once per call that ends the wait; walls are the
    explicit walls of the game's first rounds, in dealing order, and the rounds after them come from the seed.

    state is read-only: commit() is the only way to replace it, and it checks the tile ownership invariant first, so a
    corrupted state never becomes the game's state: the raise lands in the server-fault path and the game ends. The
    initial state is checked by start_game's first commit, before any event leaves the engine.
    """

    def __init__(
        self,
        *,
        game_id: str,
        state: MahjongGameState,
        ai: AIPlayerController,
        walls: Sequence[Sequence[int]] = (),
    ) -> None:
        self.game_id = game_id
        self.walls = tuple(tuple(wall) for wall in walls)
        self._state = state
        self.ai = ai
        self.furiten = FuritenTracker()
        self.first_draw_pending = False
        self.wait_id: int = 0

    @property
    def state(self) -> MahjongGameState:
        """
        The game's current state.
        """
        return self._state

    def commit(self, state: MahjongGameState) -> None:
        """
        Make state the game's state after verifying it owns every tile exactly once.
        """
        verify_tile_ownership(state)
        self._state = state
