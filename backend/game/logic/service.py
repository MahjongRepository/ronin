from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from game.logic.enums import GameAction, TimeoutType, WaitKind
    from game.logic.events import ServiceEvent
    from game.logic.runtime import GameRuntime
    from game.logic.settings import GameSettings
    from game.logic.types import ReconnectionSnapshot


@dataclass(frozen=True)
class Awaiting:
    """
    The input the game waits for after an engine call.

    seats are the awaited seats an AI player does not hold: the turn's seat, the callers still to respond to the call
    prompt, or the seats still to confirm the round end; none once the game is over. wait_id identifies the wait: it
    changes exactly when a call ends the current wait (an error result, a partial prompt response or confirmation, and a
    replacement that resolves nothing keep it), so a later wait of the same kind for the same seat gets a new one.
    round_number is the round the wait belongs to; a round advance belongs to the round that ended. results_shown is how
    many results a round advance shows in turn (one per winner of a double ron), one for any other wait.
    """

    kind: WaitKind
    seats: frozenset[int]
    wait_id: int
    round_number: int
    results_shown: int = 1


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
    The outcome of starting a game: its runtime, initial events, what it waits for, and each input player's seat.

    The caller owns the runtime: every later call on the game takes it, and dropping it disposes the game. The seats
    are in input order.
    """

    runtime: GameRuntime
    events: list[ServiceEvent]
    awaiting: Awaiting
    seats: tuple[int, ...]


class GameService(Protocol):
    """
    Interface of the game logic, used by the session and the replay runner.

    Players are identified by seat; names are display only. Every event carries its routing target: a BroadcastTarget
    (every player in the game) or a SeatTarget (only the player at that seat). Every call that can change the game
    returns what it waits for next (Awaiting). The service holds no game: start_game returns the game's GameRuntime, and
    every later call takes it.
    """

    def handle_action(
        self,
        runtime: GameRuntime,
        *,
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

        Returns the game's runtime, the initial state events (one per player with their view), the first wait and each
        input player's seat, in input order. When seed is provided, the game is deterministically reproducible. When
        seed is None, a random seed is generated. When settings is provided, the game uses the given settings. When wall
        is provided, use it instead of generating from seed.
        """
        ...

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        """
        Return what a running game waits for now, with the seats as the AI players hold them at this moment.
        """
        ...

    def handle_timeout(
        self,
        runtime: GameRuntime,
        *,
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

    def replace_with_ai_player(self, runtime: GameRuntime, seat: int) -> None:
        """
        Replace a disconnected player with an AI player at their seat.

        Called when a player disconnects mid-game.
        """
        ...

    def process_ai_player_actions_after_replacement(
        self,
        runtime: GameRuntime,
        seat: int,
    ) -> GameUpdate:
        """
        Process pending AI player actions after a player was replaced with an AI player.

        Handles the case where the replaced player had a pending turn or call.
        """
        ...

    def restore_human_player(self, runtime: GameRuntime, seat: int) -> None:
        """
        Remove the AI player at a seat and restore it for human control.
        """
        ...

    def build_reconnection_snapshot(self, runtime: GameRuntime, seat: int) -> ReconnectionSnapshot:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.

        Must be called after restore_human_player() so the AI player flag is correct.
        """
        ...

    def build_turn_event_for_seat(self, runtime: GameRuntime, seat: int) -> list[ServiceEvent]:
        """
        Rebuild the event that opened the seat's turn: its draw with its available actions, or the turn event right
        after its own pon or chi; none when the turn is not the seat's.
        """
        ...
