from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from game.logic.enums import GameAction, TimeoutType, WaitKind
    from game.logic.events import ServiceEvent
    from game.logic.settings import GameSettings
    from game.logic.state import MahjongGameState
    from game.logic.types import ReconnectionSnapshot


@dataclass(frozen=True)
class Awaiting:
    """
    The input the game waits for after an engine call.

    seats are the awaited seats an AI player does not hold: the turn's seat, the callers still to respond to the call
    prompt, or the seats still to confirm the round end; none once the game is over. wait_id identifies the wait: it
    changes exactly when a call ends the current wait (an error result, a partial prompt response or confirmation, and a
    replacement that resolves nothing keep it), so a later wait of the same kind for the same seat gets a new one.
    round_number is the round the wait belongs to; a round advance belongs to the round that ended.
    """

    kind: WaitKind
    seats: frozenset[int]
    wait_id: int
    round_number: int


@dataclass(frozen=True)
class GameUpdate:
    """
    The outcome of an engine call: the events to deliver and what the game waits for next.
    """

    events: list[ServiceEvent]
    awaiting: Awaiting


@dataclass(frozen=True)
class GameStart:
    """
    The outcome of starting a game: its initial events, what it waits for, and each input player's seat in input order.
    """

    events: list[ServiceEvent]
    awaiting: Awaiting
    seats: tuple[int, ...]


class GameService(Protocol):
    """
    Interface of the game logic, used by the session and the replay runner.

    Players are identified by seat; names are display only. Every event carries its routing target: a BroadcastTarget
    (every player in the game) or a SeatTarget (only the player at that seat). Every call that can change the game
    returns what it waits for next (Awaiting).
    """

    def handle_action(
        self,
        *,
        game_id: str,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> GameUpdate:
        """
        Handle a game action from the player at a seat.

        Returns the events to deliver and the next wait.
        """
        ...

    def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> GameStart:
        """
        Start a game with the given players, seating AI players in the empty seats.

        Returns the initial state events (one per player with their view), the first wait and each input player's seat,
        in input order. When seed is provided, the game is deterministically reproducible. When seed is None, a random
        seed is generated. When settings is provided, the game uses the given settings. When wall is provided, use it
        instead of generating from seed.
        """
        ...

    def get_game_seed(self, game_id: str) -> str | None:
        """
        Return the seed for a game, or None if game doesn't exist.
        """
        ...

    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        """
        Return the current game state, or None if game doesn't exist.
        """
        ...

    def get_awaiting(self, game_id: str) -> Awaiting:
        """
        Return what a running game waits for now, with the seats as the AI players hold them at this moment.
        """
        ...

    def handle_timeout(
        self,
        *,
        game_id: str,
        seat: int,
        timeout_type: TimeoutType,
    ) -> GameUpdate:
        """
        Handle a seat's timeout by performing the default action.

        For TURN timeout: tsumogiri (discard last drawn tile).
        For MELD timeout: pass on the call opportunity.
        For ROUND_ADVANCE timeout: auto-confirm round advancement.
        """
        ...

    def cleanup_game(self, game_id: str) -> None:
        """
        Remove all game state for a game that was abandoned or cleaned up externally.
        """
        ...

    def replace_with_ai_player(self, game_id: str, seat: int) -> None:
        """
        Replace a disconnected player with an AI player at their seat.

        Called when a player disconnects mid-game.
        """
        ...

    def process_ai_player_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> GameUpdate:
        """
        Process pending AI player actions after a player was replaced with an AI player.

        Handles the case where the replaced player had a pending turn or call.
        """
        ...

    def restore_human_player(self, game_id: str, seat: int) -> None:
        """
        Remove the AI player at a seat and restore it for human control.
        """
        ...

    def build_reconnection_snapshot(self, game_id: str, seat: int) -> ReconnectionSnapshot | None:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.

        Must be called after restore_human_player() so the AI player flag is correct.
        """
        ...

    def build_draw_event_for_seat(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """
        Rebuild the draw event with available actions for a specific seat.
        """
        ...

    def is_round_advance_pending(self, game_id: str) -> bool:
        """
        Check if a round advance is waiting for player confirmation.
        """
        ...

    def get_pending_round_advance_seats(self, game_id: str) -> list[int]:
        """
        Return the seats that still need to confirm round advance, in seat order.
        """
        ...
