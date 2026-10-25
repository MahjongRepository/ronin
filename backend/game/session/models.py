from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import asyncio

    from game.logic.runtime import GameRuntime
    from game.logic.service import Awaiting
    from game.messaging.protocol import ConnectionProtocol
    from game.session.replay_collector import ReplayRecord
    from game.session.timer import TimerConfig, TurnTimer
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

    The seat is bound once, at the start, from the engine's assignment for this participant's spec. The participant is
    connected while it has a connection. Its timer lives as long as the participant, so its bank survives a disconnect.
    """

    spec: PlayerSpec
    game: GameSession
    timer: TurnTimer
    seat: int | None = None
    connection: ConnectionProtocol | None = None

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


@dataclass(eq=False)
class GameSession:
    """
    A game in the session layer: its participants, pacing, lifecycle, engine runtime and what its end needs.

    runtime is the engine's game, held from the start until the end claim drops it. awaiting is what the engine last
    reported the game waits for (set from the start on); the session drives the timers from it and checks an action's
    wait id against it. start_record is the game's record as posted at the start (seat order, every seat's name and
    user_id); every finish record is built from it. replay holds the lines recorded since the start until the end claim
    detaches them. start_pause is the sleeping task that holds back the first deal while the game start shows; while it
    is set, awaiting is still None.
    """

    game_id: str
    timer_config: TimerConfig
    participants: list[Participant] = field(default_factory=list)
    lifecycle: GameLifecycle = GameLifecycle.PENDING
    runtime: GameRuntime | None = None
    awaiting: Awaiting | None = None
    start_record: PlayedGame | None = None
    replay: ReplayRecord | None = None
    pending_timeout: asyncio.Task[None] | None = None
    start_pause: asyncio.Task[None] | None = None

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
        Return the participant bound to a seat, or None for an AI seat.
        """
        return next((participant for participant in self.participants if participant.seat == seat), None)
