"""Shared helpers for replay integration tests."""

from typing import TYPE_CHECKING

from game.logic.enums import GameAction, GamePhase
from game.logic.events import EventType, ServiceEvent
from game.logic.mahjong_service import MahjongGameService
from game.replay.models import ReplayInput, ReplayInputEvent, ReplayTrace

if TYPE_CHECKING:
    from collections.abc import Callable

PLAYER_NAMES: tuple[str, str, str, str] = ("Alice", "Bob", "Charlie", "Diana")
SEED = 42.0


def build_replay_from_input_events(
    seed: float = SEED,
    player_names: tuple[str, str, str, str] = PLAYER_NAMES,
    input_events: list[ReplayInputEvent] | None = None,
) -> ReplayInput:
    """Build ReplayInput from explicit ReplayInputEvent inputs."""
    return ReplayInput(seed=seed, player_names=player_names, events=tuple(input_events or []))


def collect_produced_events(trace: ReplayTrace) -> list[ServiceEvent]:
    """Flatten all emitted events from trace steps into a single list."""
    return [event for step in trace.steps for event in step.emitted_events]


def find_produced_event(
    produced_events: list[ServiceEvent],
    event_type: EventType,
    *,
    predicate: Callable[[ServiceEvent], bool] | None = None,
) -> ServiceEvent:
    """Locate a specific event by type with an optional predicate.

    Raise AssertionError when absent so test failures are clear.
    """
    for event in produced_events:
        if event.event == event_type and (predicate is None or predicate(event)):
            return event
    raise AssertionError(f"No {event_type.value} event found in produced events")


async def probe_current_player(seed: float = SEED) -> tuple[str, int]:
    """Start a temporary game to discover the current player and a valid tile to discard."""
    svc = MahjongGameService(auto_cleanup=False)
    try:
        await svc.start_game("probe", list(PLAYER_NAMES), seed=seed)
        state = svc.get_game_state("probe")
        assert state is not None  # noqa: S101
        seat = state.round_state.current_player_seat
        player = state.round_state.players[seat]
        return player.name, player.tiles[-1]
    finally:
        svc.cleanup_game("probe")


async def build_discard_sequence(seed: float, count: int) -> list[ReplayInputEvent]:
    """Build a sequence of valid human actions by simulating the game forward.

    Each player discards their last tile (tsumogiri pattern).
    When call prompts appear, all pending humans pass.
    """
    svc = MahjongGameService(auto_cleanup=False)
    input_events: list[ReplayInputEvent] = []
    try:
        await svc.start_game("seq-probe", list(PLAYER_NAMES), seed=seed)

        for _ in range(count * 3):
            state = svc.get_game_state("seq-probe")
            assert state is not None  # noqa: S101
            if state.game_phase == GamePhase.FINISHED:
                break
            if len(input_events) >= count:
                break

            if state.round_state.pending_call_prompt is not None:
                for ps in sorted(state.round_state.pending_call_prompt.pending_seats):
                    pname = state.round_state.players[ps].name
                    input_events.append(ReplayInputEvent(player_name=pname, action=GameAction.PASS))
                    await svc.handle_action("seq-probe", pname, GameAction.PASS, {})
                continue

            seat = state.round_state.current_player_seat
            player = state.round_state.players[seat]
            if not player.tiles:
                break
            tile_id = player.tiles[-1]
            input_events.append(
                ReplayInputEvent(
                    player_name=player.name,
                    action=GameAction.DISCARD,
                    data={"tile_id": tile_id},
                )
            )
            await svc.handle_action("seq-probe", player.name, GameAction.DISCARD, {"tile_id": tile_id})

            if svc.is_round_advance_pending("seq-probe"):
                for human_name in svc.get_pending_round_advance_human_names("seq-probe"):
                    await svc.handle_action("seq-probe", human_name, GameAction.CONFIRM_ROUND, {})
        return input_events
    finally:
        svc.cleanup_game("seq-probe")
