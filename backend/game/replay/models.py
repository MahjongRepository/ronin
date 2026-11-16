from pydantic import BaseModel, ConfigDict, model_validator

from game.engine import (
    NUM_PLAYERS,
    NUM_TILES,
    RNG_VERSION,
    Action,
    GameEvent,
    MahjongGameState,
    Refusal,
    StartPosition,
)


class ReplayInputEvent(BaseModel):
    """
    A single player input event in a replay sequence.
    """

    model_config = ConfigDict(frozen=True)

    player_name: str
    action: Action


class ReplayInput(BaseModel):
    """
    Versioned input for deterministic replay execution.

    Enforces exactly 4 unique player names (4-player replay contract). All events must target declared players. walls
    and start are a staged game's setup for its re-run (see GameService.start_game), never read from a replay file.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    seed: str
    rng_version: str = RNG_VERSION
    player_names: tuple[str, str, str, str]
    events: tuple[ReplayInputEvent, ...]
    walls: tuple[tuple[int, ...], ...] = ()
    start: StartPosition | None = None

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

        for wall in self.walls:
            if len(wall) != NUM_TILES:
                raise ValueError(
                    f"ReplayInput.walls must hold walls of exactly {NUM_TILES} tiles, got {len(wall)}",
                )

            if sorted(wall) != list(range(NUM_TILES)):
                raise ValueError(
                    f"ReplayInput.walls must each be a permutation of tile IDs 0..{NUM_TILES - 1}",
                )

        return self


class ReplayStep(BaseModel):
    """
    One replay transition: state_before + input -> emitted events + state_after.

    A round advance has no input: the runner deals the next round and lets its dealer draw, as a synthetic step. A
    refused input, kept only outside strict mode, emits nothing and carries its refusal.
    """

    model_config = ConfigDict(frozen=True)

    input_event: ReplayInputEvent | None
    synthetic: bool = False
    emitted_events: tuple[GameEvent, ...]
    refusal: Refusal | None = None
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

    @property
    def events(self) -> tuple[GameEvent, ...]:
        """
        Every event the replay emitted, in order: the startup events, then each step's.
        """
        return (*self.startup_events, *(event for step in self.steps for event in step.emitted_events))


class ReplayError(Exception):
    """
    Raised when the engine refuses a replay step's input: any refusal in strict mode, a not-offered one in either.
    """

    def __init__(self, step_index: int, event: ReplayInputEvent, refusal: Refusal) -> None:
        self.step_index = step_index
        self.event = event
        self.refusal = refusal
        super().__init__(
            f"Replay error at step {step_index} ({event.action} by {event.player_name}): "
            f"refused {refusal.kind.value}: {refusal.code.value}",
        )


class ReplayStepLimitError(Exception):
    """
    Raised when replay exceeds max allowed steps.
    """


class ReplayInputAfterGameEndError(Exception):
    """
    Raised when replay contains extra input after game end in strict mode.
    """
