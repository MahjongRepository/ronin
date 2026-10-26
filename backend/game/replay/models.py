from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from game.logic.enums import GameAction
from game.logic.events import ErrorEvent, GameEvent
from game.logic.rng import RNG_VERSION
from game.logic.settings import NUM_PLAYERS, GameSettings
from game.logic.state import MahjongGameState
from game.logic.tiles import NUM_TILES


class ReplayInputEvent(BaseModel):
    """
    A single player input event in a replay sequence.
    """

    model_config = ConfigDict(frozen=True)

    player_name: str
    action: GameAction
    data: dict[str, Any] = Field(default_factory=dict)


class ReplayInput(BaseModel):
    """
    Versioned input for deterministic replay execution.

    Enforces exactly 4 unique player names (4-player replay contract). All events must target declared players.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    seed: str
    rng_version: str = RNG_VERSION
    player_names: tuple[str, str, str, str]
    settings: GameSettings
    events: tuple[ReplayInputEvent, ...]
    wall: tuple[int, ...] | None = None

    @model_validator(mode="after")
    def _validate_replay_input(self) -> ReplayInput:
        if len(set(self.player_names)) != NUM_PLAYERS:
            raise ValueError(f"ReplayInput.player_names must contain {NUM_PLAYERS} unique names")

        player_name_set = set(self.player_names)
        invalid_names = {event.player_name for event in self.events if event.player_name not in player_name_set}
        if invalid_names:
            raise ValueError(
                f"ReplayInput.events contain unknown player_name values: {sorted(invalid_names)}",
            )

        if self.wall is not None:
            if len(self.wall) != NUM_TILES:
                raise ValueError(
                    f"ReplayInput.wall must contain exactly {NUM_TILES} tiles, got {len(self.wall)}",
                )

            if sorted(self.wall) != list(range(NUM_TILES)):
                raise ValueError(
                    f"ReplayInput.wall must be a permutation of tile IDs 0..{NUM_TILES - 1}",
                )

        return self


class ReplayStep(BaseModel):
    """
    One replay transition: state_before + input -> emitted events + state_after.
    """

    model_config = ConfigDict(frozen=True)

    input_event: ReplayInputEvent
    synthetic: bool = False
    emitted_events: tuple[GameEvent, ...]
    state_before: MahjongGameState
    state_after: MahjongGameState


class ReplayTrace(BaseModel):
    """
    Complete output of a replay execution.
    """

    model_config = ConfigDict(frozen=True)

    seed: str
    rng_version: str = RNG_VERSION
    seat_by_player: dict[str, int]
    startup_events: tuple[GameEvent, ...]
    initial_state: MahjongGameState
    steps: tuple[ReplayStep, ...]
    final_state: MahjongGameState


class ReplayError(Exception):
    """
    Raised when a replay step produces an error event in strict mode.
    """

    def __init__(self, step_index: int, event: ReplayInputEvent, errors: list[GameEvent]) -> None:
        self.step_index = step_index
        self.event = event
        self.errors = errors

        messages = [e.message for e in errors if isinstance(e, ErrorEvent)]
        super().__init__(
            f"Replay error at step {step_index} ({event.action} by {event.player_name}): "
            f"{len(errors)} error(s): {messages}",
        )


class ReplayStepLimitError(Exception):
    """
    Raised when replay exceeds max allowed steps.
    """


class ReplayInputAfterGameEndError(Exception):
    """
    Raised when replay contains extra input after game end in strict mode.
    """
