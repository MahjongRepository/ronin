from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.logic.enums import GameAction, TimeoutType, WaitKind
    from game.logic.events import GameEvent
    from game.logic.runtime import GameRuntime
    from game.logic.types import ReconnectionSnapshot, StartPosition


@dataclass(frozen=True)
class Awaiting:
    """
    The input the game waits for after an engine call.

    seats are the awaited seats an AI player does not hold: the turn's seat or the callers still to respond to the call
    prompt; none for an AI player's turn, a dealt round whose dealer has not drawn yet (begin_round draws), a round over
    (deal_next_round deals the next) or a game over. wait_id identifies the wait: it changes exactly when a call ends
    the current wait (an error result, a partial prompt response, and a replacement or restore that resolves nothing
    keep it), so a later wait of the same kind for the same seat gets a new one. round_number is the round the wait
    belongs to; a round over belongs to the round that ended.
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

    events: list[GameEvent]
    awaiting: Awaiting


@dataclass(frozen=True)
class GameStart:
    """
    The outcome of starting a game: its runtime, initial events, what it waits for, and each input player's seat.

    The caller owns the runtime: every later call on the game takes it, and dropping it disposes the game. The seats
    are in input order.
    """

    runtime: GameRuntime
    events: list[GameEvent]
    awaiting: Awaiting
    seats: tuple[int, ...]


class GameService(Protocol):
    """
    Interface of the game logic, used by the session and the replay runner.

    Players are identified by seat; names are display only. Every event carries its routing target: a BroadcastTarget
    (every player in the game) or a SeatTarget (only the player at that seat). Every call that can change the game
    returns what it waits for next (Awaiting). The service holds no game: start_game returns the game's GameRuntime, and
    every later call takes it. A service that paces AI turns stops before each AI player's turn action and reports it as
    a WaitKind.AI_TURN wait, which advance_ai_turn plays; AI responses to call prompts never wait.
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
        walls: Sequence[Sequence[int]] = (),
        start: StartPosition | None = None,
    ) -> GameStart:
        """
        Start a game with the given players, seating AI players in the empty seats.

        Returns the game's runtime, the initial state events (one per player with their view), the first wait and each
        input player's seat, in input order. When seed is provided, the game is deterministically reproducible. When
        seed is None, a random seed is generated. Every game plays the one rules preset. The game's first rounds are
        dealt from walls, one 136-tile wall each, in order, and the rounds after them from the seed; a round dealt from
        a given wall breaks it at dice (1, 1), and given walls make seat 0 the first dealer. A start position starts the
        game at its scores, sticks, dealer, wind and round number in place of East 1. The game stops after the first
        deal (WaitKind.DEALT): its dealer draws only on begin_round.
        """
        ...

    def begin_round(self, runtime: GameRuntime) -> GameUpdate:
        """
        Draw the dealt round's first tile for its dealer (WaitKind.DEALT), with the AI turns that follow it.

        Returns the events to deliver and the next wait. Calling it on any other wait is a server fault.
        """
        ...

    def deal_next_round(self, runtime: GameRuntime) -> GameUpdate:
        """
        Deal the round after the one that ended (WaitKind.ROUND_OVER), from the game's next given wall or else its seed.

        Returns the deal's events and the next wait, a dealt round (WaitKind.DEALT). Calling it on any other wait is a
        server fault.
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

    def restore_human_player(self, runtime: GameRuntime, seat: int) -> Awaiting:
        """
        Remove the AI player at a seat and restore it for human control; return what the game waits for now.

        An AI player's turn the seat was owed becomes the human's turn, a new wait; any other wait is kept.
        """
        ...

    def advance_ai_turn(self, runtime: GameRuntime) -> GameUpdate:
        """
        Play the AI player's turn the game waits for (WaitKind.AI_TURN): exactly one turn action, with the AI call
        responses and the round end it leads to.

        Returns the events to deliver and the next wait. Calling it on any other wait is a server fault.
        """
        ...

    def build_reconnection_snapshot(self, runtime: GameRuntime, seat: int) -> ReconnectionSnapshot:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.

        For a seat an AI player held, call it after restore_human_player() so the AI player flag is correct.
        """
        ...

    def build_wait_events_for_seat(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
        """
        Rebuild the event that opened the wait the game owes the seat: its call prompt, or its turn's draw with its
        available actions (the turn event right after its own pon or chi); none for a wait that does not await the seat.
        """
        ...
