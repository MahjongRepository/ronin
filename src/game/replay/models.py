"""
Replay data models: input, output trace, and error types.

ReplayInput is the versioned input format for deterministic replay.
ReplayTrace is the output containing explicit state transitions per step.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from game.logic.enums import GameAction
from game.logic.state import MahjongGameState
from game.messaging.events import ErrorEvent, ServiceEvent

REQUIRED_PLAYER_COUNT = 4


class ReplayInputEvent(BaseModel):
    """A single human input event in a replay sequence."""

    model_config = ConfigDict(frozen=True)

    player_name: str
    action: GameAction
    data: dict[str, Any] = Field(default_factory=dict)


class ReplayInput(BaseModel):
    """
    Versioned input for deterministic replay execution.

    Enforces exactly 4 unique player names (4-human replay contract).
    All events must target declared players.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    seed: float
    player_names: tuple[str, str, str, str]
    events: tuple[ReplayInputEvent, ...]

    @model_validator(mode="after")
    def _validate_player_names(self) -> ReplayInput:
        if len(set(self.player_names)) != REQUIRED_PLAYER_COUNT:
            raise ValueError("ReplayInput.player_names must contain 4 unique names")
        player_name_set = set(self.player_names)
        invalid_names = {
            event.player_name for event in self.events if event.player_name not in player_name_set
        }
        if invalid_names:
            raise ValueError(
                f"ReplayInput.events contain unknown player_name values: {sorted(invalid_names)}"
            )
        return self


class ReplayStep(BaseModel):
    """One replay transition: state_before + input -> emitted events + state_after."""

    model_config = ConfigDict(frozen=True)

    input_event: ReplayInputEvent
    synthetic: bool = False
    emitted_events: tuple[ServiceEvent, ...]
    state_before: MahjongGameState
    state_after: MahjongGameState


class ReplayTrace(BaseModel):
    """Complete output of a replay execution."""

    model_config = ConfigDict(frozen=True)

    seed: float
    seat_by_player: dict[str, int]
    startup_events: tuple[ServiceEvent, ...]
    initial_state: MahjongGameState
    steps: tuple[ReplayStep, ...]
    final_state: MahjongGameState


class ReplayError(Exception):
    """Raised when a replay step produces an error event in strict mode."""

    def __init__(self, step_index: int, event: ReplayInputEvent, errors: list[ServiceEvent]) -> None:
        self.step_index = step_index
        self.event = event
        self.errors = errors
        messages = [e.data.message for e in errors if isinstance(e.data, ErrorEvent)]
        super().__init__(
            f"Replay error at step {step_index} ({event.action} by {event.player_name}): {messages}"
        )


class ReplayStartupError(Exception):
    """Raised when start_game emits error events in strict mode."""


class ReplayStepLimitError(Exception):
    """Raised when replay exceeds max allowed steps."""


class ReplayInputAfterGameEndError(Exception):
    """Raised when replay contains extra input after game end in strict mode."""


class ReplayInvariantError(Exception):
    """Raised when the engine violates replay-required invariants."""
