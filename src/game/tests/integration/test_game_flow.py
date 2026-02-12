"""
Integration tests for Mahjong game flow.

Tests service-level game creation event contract and end-to-end
discard cycle through MahjongGameService.
"""

import pytest

from game.logic.enums import CallType, GameAction, RoundPhase
from game.logic.events import BroadcastTarget, CallPromptEvent, EventType, GameStartedEvent, SeatTarget
from game.logic.mahjong_service import MahjongGameService


class TestGameCreationAndJoin:
    """Test game creation and initial state delivery."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_create_game_and_join_returns_initial_state(self, service):
        """Create game and verify game_started broadcast event is received."""
        events = await service.start_game("game1", ["Human"], seed=2.0)

        game_started_events = [e for e in events if e.event == EventType.GAME_STARTED]
        assert len(game_started_events) == 1

        event = game_started_events[0]
        assert isinstance(event.data, GameStartedEvent)
        assert event.target == BroadcastTarget()
        assert event.data.game_id == "game1"
        assert len(event.data.players) == 4

        for player in event.data.players:
            assert player.seat is not None
            assert player.name is not None


class TestGameServiceIntegration:
    """Integration tests using MahjongGameService."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_full_discard_cycle(self, service):
        """Test human discard triggers bot turns and returns to human."""
        events = await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # find the human player (seat is random now)
        human = next(p for p in round_state.players if p.name == "Human")

        # human needs to have tiles to discard
        assert len(human.tiles) >= 13
        tile_to_discard = human.tiles[-1]

        events = await service.handle_action(
            "game1",
            "Human",
            GameAction.DISCARD,
            {"tile_id": tile_to_discard},
        )

        # should have discard event
        discard_events = [e for e in events if e.event == EventType.DISCARD]
        assert len(discard_events) >= 1

    async def test_sequential_discards_through_service(self, service):
        """Test that multiple human discards can be processed sequentially."""
        await service.start_game("game1", ["Human"], seed=2.0)

        actions_processed = 0

        # play several discards (bots will respond automatically)
        for _ in range(10):
            game_state = service._games["game1"]
            round_state = game_state.round_state
            if round_state.phase == RoundPhase.FINISHED:
                break

            current_seat = round_state.current_player_seat
            player = round_state.players[current_seat]

            if player.name == "Human" and player.tiles:
                tile_to_discard = player.tiles[-1]
                await service.handle_action(
                    "game1",
                    player.name,
                    GameAction.DISCARD,
                    {"tile_id": tile_to_discard},
                )
                actions_processed += 1

        assert actions_processed >= 2, "expected multiple discards to be processed"


class TestUnifiedDiscardClaimIntegration:
    """Integration test for unified DISCARD prompt through MahjongGameService."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_per_seat_call_prompts_never_use_raw_discard(self, service):
        """Per-seat call prompt events use RON or MELD call_type, never raw DISCARD.

        Plays multiple discards to maximize the chance of observing call prompts.
        Verifies the wire contract: DISCARD prompts are split per-seat with the
        appropriate call_type for each recipient.
        """
        await service.start_game("game1", ["Human"], seed=2.0)

        found_prompt = False
        for _ in range(20):
            game_state = service._games["game1"]
            round_state = game_state.round_state
            if round_state.phase == RoundPhase.FINISHED:
                break

            current_seat = round_state.current_player_seat
            player = round_state.players[current_seat]
            if player.name != "Human" or not player.tiles:
                break

            tile_to_discard = player.tiles[-1]
            events = await service.handle_action(
                "game1",
                "Human",
                GameAction.DISCARD,
                {"tile_id": tile_to_discard},
            )

            call_prompt_events = [e for e in events if e.event == EventType.CALL_PROMPT]
            for cp_event in call_prompt_events:
                found_prompt = True
                assert isinstance(cp_event.data, CallPromptEvent)
                # per-seat events are split: RON or MELD, not raw DISCARD
                assert cp_event.data.call_type in (CallType.RON, CallType.MELD), (
                    f"expected per-seat call_type RON or MELD, got {cp_event.data.call_type}"
                )
                assert isinstance(cp_event.target, SeatTarget)

        assert found_prompt, "expected at least one call prompt event across multiple discards"

    async def test_discard_prompt_creates_unified_prompt_in_state(self, service):
        """When a discard creates a call prompt, the server state has call_type=DISCARD."""
        await service.start_game("game1", ["Human"], seed=2.0)

        found_discard_prompt = False
        for _ in range(20):
            game_state = service._games["game1"]
            round_state = game_state.round_state
            if round_state.phase == RoundPhase.FINISHED:
                break

            current_seat = round_state.current_player_seat
            player = round_state.players[current_seat]
            if player.name != "Human" or not player.tiles:
                break

            tile_to_discard = player.tiles[-1]
            await service.handle_action(
                "game1",
                player.name,
                GameAction.DISCARD,
                {"tile_id": tile_to_discard},
            )

            # check if a DISCARD prompt was created in server state
            game_state = service._games["game1"]
            round_state = game_state.round_state
            prompt = round_state.pending_call_prompt
            if prompt is not None and prompt.call_type == CallType.DISCARD:
                found_discard_prompt = True
                break

        assert found_discard_prompt, (
            "expected at least one DISCARD prompt in server state across multiple discards"
        )
