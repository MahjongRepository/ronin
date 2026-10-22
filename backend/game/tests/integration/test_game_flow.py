import pytest

from game.logic.enums import CallType, GameAction, RoundPhase
from game.logic.events import BroadcastTarget, CallPromptEvent, EventType, GameStartedEvent, SeatTarget
from game.logic.mahjong_service import MahjongGameService


class TestGameCreationAndJoin:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_start_game__when_one_human_joins__should_emit_game_started_with_four_players(self, service):
        events = service.start_game("game1", ["Player"], seed="a" * 192).events
        game_started_events = [e for e in events if e.event == EventType.GAME_STARTED]
        assert len(game_started_events) == 1
        event = game_started_events[0]
        assert isinstance(event.data, GameStartedEvent)
        assert event.target == BroadcastTarget()
        assert event.data.game_id == "game1"
        assert event.data.dealer_seat in range(4)
        assert len(event.data.players) == 4
        for player in event.data.players:
            assert player.seat is not None
            assert player.name is not None


class TestGameServiceIntegration:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_human_discards_repeatedly__should_process_multiple_discards(self, service):
        human_seat = service.start_game("game1", ["Player"], seed="a" * 192).seats[0]

        actions_processed = 0
        # play several discards (AI players will respond automatically)
        for _ in range(10):
            game_state = service.get_game_state("game1")
            if game_state is None or game_state.round_state.phase == RoundPhase.FINISHED:
                break

            round_state = game_state.round_state
            current_seat = round_state.current_player_seat
            player = round_state.players[current_seat]

            if current_seat == human_seat and player.tiles:
                tile_to_discard = player.tiles[-1]
                service.handle_action(
                    game_id="game1",
                    seat=human_seat,
                    action=GameAction.DISCARD,
                    data={"tile_id": tile_to_discard},
                )
                actions_processed += 1

        assert actions_processed >= 2, "expected multiple discards to be processed"


class TestUnifiedDiscardClaimIntegration:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_call_prompt__when_discard_claimable__should_split_per_seat_into_ron_or_meld(self, service):
        human_seat = service.start_game("game1", ["Player"], seed="a" * 192).seats[0]

        found_prompt = False
        for _ in range(20):
            game_state = service.get_game_state("game1")
            if game_state is None or game_state.round_state.phase == RoundPhase.FINISHED:
                break

            round_state = game_state.round_state
            current_seat = round_state.current_player_seat
            player = round_state.players[current_seat]
            if current_seat != human_seat or not player.tiles:
                break

            tile_to_discard = player.tiles[-1]
            events = service.handle_action(
                game_id="game1",
                seat=human_seat,
                action=GameAction.DISCARD,
                data={"tile_id": tile_to_discard},
            ).events
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
