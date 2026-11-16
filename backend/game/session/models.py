from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import asyncio

    from game.engine import Awaiting, GameRuntime
    from game.messaging.protocol import ConnectionProtocol
    from game.messaging.roster import GameRoster
    from game.session.replay_collector import ReplayRecord
    from game.session.timer import TimerConfig, TurnTimer
    from game.wire.enums import SeatControlReason
    from shared.dal.models import PlayedGame


class PlayerSpec(BaseModel):
    """
    Player info for direct game creation.

    The game_ticket field is the signed game ticket string: the game server keys the player's participant by it for the
    whole game, so clients present the same ticket in JOIN_GAME and RECONNECT.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=100)
    game_ticket: str = Field(min_length=1, max_length=2000)


class GameLifecycle(StrEnum):
    """
    Where a game is in its life: PENDING → PLAYING → ENDING → CLOSED, or PENDING → ENDING.

    PENDING waits for the expected humans' JOIN_GAME; PLAYING is set synchronously at the start; ENDING is claimed once,
    synchronously, by the one end (completion, failure or abandonment), which also releases the game from the registry;
    CLOSED is set by the finalizer once the end's effects (replay, finish record, closes) are done.
    """

    PENDING = "pending"
    PLAYING = "playing"
    ENDING = "ending"
    CLOSED = "closed"


@dataclass(eq=False)
class Participant:
    """
    One expected human of a game, from POST /games to the game's end, across any number of connections.

    The seat is bound once, at the start, from the session's seating of this participant's spec. The participant is
    connected while it has a connection. Its timer lives as long as the participant, so its bank survives a disconnect.
    stand_in says why an AI player holds its seat, from the handover until the participant takes the seat back.
    decision_id counts only decisions opened while connected; other seats and AI play never advance it.
    """

    spec: PlayerSpec
    game: GameSession
    timer: TurnTimer
    seat: int | None = None
    connection: ConnectionProtocol | None = None
    stand_in: SeatControlReason | None = None
    decision_id: int = 0

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def user_id(self) -> str:
        return self.spec.user_id

    @property
    def ticket(self) -> str:
        return self.spec.game_ticket

    @property
    def is_connected(self) -> bool:
        return self.connection is not None


@dataclass(frozen=True)
class Pause:
    """
    A pause the session holds a game in until its seats confirm it: the game's start, between the first deal and the
    dealer's first draw, or a round's end, before the next round's deal.

    seats are the seats that still owe their confirmation: the connected participants' when the pause opened, each
    leaving once it confirms, its timer confirms for it or it disconnects. results_shown is how many results a round's
    end shows its players one after another: one per winner of a double ron, else one, and one for the game's start.
    """

    starts_game: bool
    seats: frozenset[int]
    results_shown: int = 1


@dataclass(eq=False)
class GameSession:
    """
    A game in the session layer: its participants, pacing, lifecycle, engine runtime and what its end needs.

    runtime is the engine's game, held from the start until the end claim drops it; roster is who sits where, under what
    name, set at the start. awaiting is what the engine last reported the game waits for (set from the start on); the
    session compares each new report with it to tell a new wait from a kept one, which drives the timers and the
    decision ids. pause is the start's or a round end's pause the session holds the game in, None otherwise. Each
    participant's decision_id identifies only their own visible decisions. start_record is the game's record as posted
    at the start (seat order, every seat's name and user_id); every finish record is built from it. replay holds the
    records collected since the start until the end claim detaches them. ai_turn is the sleeping task that plays the AI
    player's turn the game waits on once the AI turn delay has passed.
    """

    game_id: str
    timer_config: TimerConfig
    participants: list[Participant] = field(default_factory=list)
    lifecycle: GameLifecycle = GameLifecycle.PENDING
    runtime: GameRuntime | None = None
    roster: GameRoster | None = None
    awaiting: Awaiting | None = None
    pause: Pause | None = None
    start_record: PlayedGame | None = None
    replay: ReplayRecord | None = None
    pending_timeout: asyncio.Task[None] | None = None
    ai_turn: asyncio.Task[None] | None = None

    @property
    def is_active(self) -> bool:
        """
        Whether the game is pending or playing: its end has not been claimed.
        """
        return self.lifecycle in (GameLifecycle.PENDING, GameLifecycle.PLAYING)

    def connected(self) -> list[Participant]:
        """
        Return the participants with a connection, in input order.
        """
        return [participant for participant in self.participants if participant.is_connected]

    def at_seat(self, seat: int) -> Participant | None:
        """
        Return the participant bound to a seat, or None for a seat no participant takes.

        A disconnected participant's seat still returns its participant though an AI player plays it: is_ai_seat is the
        test for an AI player's seat.
        """
        return next((participant for participant in self.participants if participant.seat == seat), None)

    def is_ai_seat(self, seat: int) -> bool:
        """
        Whether an AI player plays a seat of the started game: a seat no participant takes, or one whose participant has
        no connection (it never joined, or it left and has not reconnected).
        """
        participant = self.at_seat(seat)
        return participant is None or not participant.is_connected
