"""Replay scenario: game-end auto-cleanup regression test.

Verify handle_action does not raise KeyError when game state is cleaned up
during game-end handling with auto_cleanup=True.
"""

from game.logic.enums import GameAction, GamePhase
from game.logic.mahjong_service import MahjongGameService
from game.messaging.events import EventType, ServiceEvent
from game.tests.integration.replays.helpers import PLAYER_NAMES, SEED


async def test_game_end_cleanup_regression():
    """Action path that ends the game returns events without raising."""
    service = MahjongGameService(auto_cleanup=True)
    await service.start_game("game1", list(PLAYER_NAMES), seed=SEED)
    produced_events: list[ServiceEvent] = []

    for _ in range(500):
        state = service.get_game_state("game1")
        if state is None:
            break
        if state.game_phase == GamePhase.FINISHED:
            break

        # Handle pending call prompts by passing for all pending humans
        if state.round_state.pending_call_prompt is not None:
            for ps in sorted(state.round_state.pending_call_prompt.pending_seats):
                pname = state.round_state.players[ps].name
                pass_events = await service.handle_action("game1", pname, GameAction.PASS, {})
                produced_events.extend(pass_events)
            continue

        seat = state.round_state.current_player_seat
        player = state.round_state.players[seat]
        if not player.tiles:
            break

        tile_id = player.tiles[-1]
        events = await service.handle_action("game1", player.name, GameAction.DISCARD, {"tile_id": tile_id})
        assert isinstance(events, list)
        produced_events.extend(events)

        if service.is_round_advance_pending("game1"):
            for human_name in service.get_pending_round_advance_human_names("game1"):
                confirm_events = await service.handle_action(
                    "game1",
                    human_name,
                    GameAction.CONFIRM_ROUND,
                    {},
                )
                produced_events.extend(confirm_events)

    terminal_event_types = {EventType.ROUND_END, EventType.GAME_END}
    assert any(event.event in terminal_event_types for event in produced_events)
