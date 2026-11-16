from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.logic.decision import Action, Decision
    from game.logic.enums import WaitKind
    from game.logic.events import GameEvent
    from game.logic.refusal import Refusal
    from game.logic.runtime import GameRuntime
    from game.logic.types import ReconnectionSnapshot, StartPosition


@dataclass(frozen=True)
class Awaiting:
    """
    The input the game waits for after an engine call.

    seats are the awaited seats an AI player does not hold: the turn's seat or the callers still to respond to the call
    prompt; none for an AI player's turn, a dealt round whose dealer has not drawn yet (begin_round draws), a round over
    (deal_next_round deals the next) or a game over. round_number is the round the wait belongs to; a round over belongs
    to the round that ended.
    """

    kind: WaitKind
    seats: frozenset[int]
    round_number: int


@dataclass(frozen=True)
class GameUpdate:
    """
    The outcome of an engine call: the events to deliver and what the game waits for next.
    """

    events: list[GameEvent]
    awaiting: Awaiting


class GameService(Protocol):
    """
    Interface of the game logic, used by the session and the replay runner.

    Players are identified by seat only: who sits where, under what name, is the caller's. Every event carries its
    routing target: a BroadcastTarget (every player in the game) or a SeatTarget (only the player at that seat). Every
    call that can change the game returns what it waits for next (Awaiting), or a Refusal that changed nothing: no call
    raises for a player's input.
    The service holds no game: new_game returns the game's GameRuntime, and every later call takes it. A service that
    paces AI turns stops before each AI player's turn action and reports it as a WaitKind.AI_TURN wait, which
    advance_ai_turn plays; AI responses to call prompts never wait.
    """

    def act(self, runtime: GameRuntime, seat: int, action: Action) -> GameUpdate | Refusal:
        """
        Apply one action of the player at a seat: a domain action, checked against the rules and what the seat was
        offered.

        Returns the events to deliver and the next wait, or the Refusal of an action a rule forbids (RULE), that the
        seat was not offered or names a tile it does not hold (NOT_OFFERED), or that the game does not await from the
        seat now (NOT_AWAITED: the round not in play, another seat's turn, an answered call, or another decision's
        action). A refusal leaves the game unchanged.
        """
        ...

    def legal_actions(self, runtime: GameRuntime, seat: int) -> tuple[Action, ...]:
        """
        Return every action the seat may take now, in offer order; none when the game does not await the seat.

        An AI player's seat on its turn counts as awaited here, though Awaiting leaves AI players' seats out.

        An action equivalent to a listed one is legal too: a chi with another held copy of an offered shape, a kan from
        any tile of an offered type.
        """
        ...

    def default_action(self, runtime: GameRuntime, seat: int) -> Action | None:
        """
        Return the action a timeout takes for the seat: the default discard on a turn, a pass on a call, never a win or
        a call; None when the game does not await the seat.

        An AI player's seat on its turn counts as awaited here, though Awaiting leaves AI players' seats out.
        """
        ...

    def decision(self, runtime: GameRuntime, seat: int) -> Decision | None:
        """
        Return the seat's decision: its context, its legal actions and its default; None when the game does not await
        the seat.

        An AI player's seat on its turn counts as awaited here, though Awaiting leaves AI players' seats out.
        """
        ...

    def new_game(
        self,
        seed: str,
        *,
        walls: Sequence[Sequence[int]] = (),
        start: StartPosition | None = None,
        ai_seats: frozenset[int] = frozenset(),
    ) -> tuple[GameRuntime, list[GameEvent]]:
        """
        Build a game from its seed and deal its first round, with AI players at ai_seats.

        Returns the game's runtime and its initial events: the game start, then one round start per seat with its view;
        get_awaiting reads its first wait. The same seed and inputs play the same game. Every game plays the one rules
        preset. The game's first rounds are dealt from walls, one 136-tile wall each, in order, and the rounds after
        them from the seed; a round dealt from a given wall breaks it at dice (1, 1), and given walls make seat 0 the
        first dealer. A start position starts the game at its scores, sticks, dealer, wind and round number in place of
        East 1. The game stops after the first deal (WaitKind.DEALT): its dealer draws only on begin_round.
        """
        ...

    def begin_round(self, runtime: GameRuntime) -> GameUpdate | Refusal:
        """
        Draw the dealt round's first tile for its dealer (WaitKind.DEALT), with the AI turns that follow it.

        Returns the events to deliver and the next wait; on any other wait a NOT_AWAITED Refusal (wrong phase).
        """
        ...

    def deal_next_round(self, runtime: GameRuntime) -> GameUpdate | Refusal:
        """
        Deal the round after the one that ended (WaitKind.ROUND_OVER), from the game's next given wall or else its seed.

        Returns the deal's events and the next wait, a dealt round (WaitKind.DEALT); on any other wait a NOT_AWAITED
        Refusal (wrong phase).
        """
        ...

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        """
        Return what a running game waits for now, with the seats as the AI players hold them at this moment.
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
        """
        ...

    def build_wait_events_for_seat(self, runtime: GameRuntime, seat: int) -> list[GameEvent]:
        """
        Rebuild the event that opened the wait the game owes the seat: its call prompt, or its turn's draw with its
        available actions (the turn event right after its own pon or chi); none for a wait that does not await the seat.
        """
        ...
