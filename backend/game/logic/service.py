from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.logic.decision import Action, Decision
    from game.logic.events import GameEvent
    from game.logic.refusal import Refusal
    from game.logic.runtime import GameRuntime
    from game.logic.types import ReconnectionSnapshot, StartPosition


@dataclass(frozen=True)
class Dealt:
    """
    A dealt round whose dealer has not drawn yet (begin_round draws its first tile); it awaits no seat.
    """

    @property
    def seats(self) -> frozenset[int]:
        return frozenset()


@dataclass(frozen=True)
class Turn:
    """
    A seat's turn: the seat it awaits, after its draw or its own pon or chi.
    """

    seat: int

    @property
    def seats(self) -> frozenset[int]:
        return frozenset({self.seat})


@dataclass(frozen=True)
class Call:
    """
    An open call: the seats still to answer the discard or the kan they may call.
    """

    seats: frozenset[int]


@dataclass(frozen=True)
class RoundOver:
    """
    A round that ended without ending the game (deal_next_round deals the next); it awaits no seat.
    """

    @property
    def seats(self) -> frozenset[int]:
        return frozenset()


@dataclass(frozen=True)
class GameOver:
    """
    A finished game; it awaits no seat.
    """

    @property
    def seats(self) -> frozenset[int]:
        return frozenset()


type Awaiting = Dealt | Turn | Call | RoundOver | GameOver


class GameService(Protocol):
    """
    Interface of the game logic, used by the session and the replay runner.

    Players are identified by seat only: who sits where, under what name and who answers each seat (a person, an AI
    player, a timeout) are the caller's. Every event carries its routing target: a BroadcastTarget (every player in the
    game) or a SeatTarget (only the player at that seat). Every call that can change the game returns its events, or a
    Refusal that changed nothing: no call raises for a player's input. What the game waits for next is a separate read
    (get_awaiting). The service holds no game: new_game returns the game's GameRuntime, and every later call takes it.
    """

    def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
        """
        Apply one answer of one seat: a domain action, checked against the rules and what the seat was offered.

        Returns the events to deliver, or the Refusal of an action a rule forbids (RULE), that the seat was not offered
        or names a tile it does not hold (NOT_OFFERED), or that the game does not await from the seat now (NOT_AWAITED:
        the round not in play, another seat's turn, an answered call, or another decision's action). A refusal leaves
        the game unchanged.
        """
        ...

    def legal_actions(self, runtime: GameRuntime, seat: int) -> tuple[Action, ...]:
        """
        Return every action the seat may take now, in offer order; none when the game does not await the seat.

        An action equivalent to a listed one is legal too: a chi with another held copy of an offered shape, a kan from
        any tile of an offered type.
        """
        ...

    def default_action(self, runtime: GameRuntime, seat: int) -> Action | None:
        """
        Return the action a timeout takes for the seat: the default discard on a turn, a pass on a call, never a win or
        a call; None when the game does not await the seat.
        """
        ...

    def decision(self, runtime: GameRuntime, seat: int) -> Decision | None:
        """
        Return the seat's decision: its context, its legal actions and its default; None when the game does not await
        the seat.
        """
        ...

    def new_game(
        self,
        seed: str,
        *,
        walls: Sequence[Sequence[int]] = (),
        start: StartPosition | None = None,
    ) -> tuple[GameRuntime, list[GameEvent]]:
        """
        Build a game from its seed and deal its first round.

        Returns the game's runtime and its initial events: the game start, then one round start per seat with its view;
        get_awaiting reads its first wait. The same seed and inputs play the same game. Every game plays the one rules
        preset. The game's first rounds are dealt from walls, one 136-tile wall each, in order, and the rounds after
        them from the seed; a round dealt from a given wall breaks it at dice (1, 1), and given walls make seat 0 the
        first dealer. A start position starts the game at its scores, sticks, dealer, wind and round number in place of
        East 1. The game stops after the first deal (Dealt): its dealer draws only on begin_round.
        """
        ...

    def begin_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
        """
        Draw the dealt round's first tile for its dealer (Dealt).

        Returns the draw's events; on any other wait a NOT_AWAITED Refusal (wrong phase).
        """
        ...

    def deal_next_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
        """
        Deal the round after the one that ended (RoundOver), from the game's next given wall or else its seed.

        Returns the deal's events, after which the game waits on the dealt round (Dealt); on any other wait a
        NOT_AWAITED Refusal (wrong phase).
        """
        ...

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        """
        Return what the game waits for now, naming every awaited seat.
        """
        ...

    def build_reconnection_snapshot(self, runtime: GameRuntime, seat: int) -> ReconnectionSnapshot:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.
        """
        ...

    def build_wait_events_for_seat(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
        """
        Rebuild the event that opened the wait the game owes the seat: its call prompt, or its turn's draw with its
        available actions (the turn event right after its own pon or chi); none for a wait that does not await the seat.
        """
        ...
