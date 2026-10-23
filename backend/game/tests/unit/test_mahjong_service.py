import logging
from dataclasses import replace

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import GameAction, KanType, PlayerAction, PromptKind, RoundPhase, WaitKind
from game.logic.events import (
    DiscardEvent,
    EventType,
    SeatTarget,
)
from game.logic.exceptions import UnsupportedSettingsError
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import GameSettings
from game.logic.state import Caller, PendingCallPrompt
from game.logic.tiles import tile_to_34
from game.logic.types import (
    ExhaustiveDrawResult,
    TenpaiHand,
)
from game.logic.wall import Wall
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceAllPlayers:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_start_game__when_four_players__should_emit_single_draw_event_for_dealer(self, service):
        events = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"]).events
        # with 4 players, exactly 1 draw event for dealer (no AI player followup chain)
        draw_events = [e for e in events if e.event == EventType.DRAW]
        assert len(draw_events) == 1


class TestMahjongGameServiceReplaceWithAIPlayer:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_replace_with_ai_player__when_player_replaced__should_register_ai_player_in_controller(self, service):
        player_seat = service.start_game("game1", ["Alice"]).seats[0]
        ai_player_controller = service._runtimes["game1"].ai
        assert ai_player_controller.is_ai_player(player_seat) is False

        service.replace_with_ai_player("game1", player_seat)
        assert ai_player_controller.is_ai_player(player_seat) is True

    def test_replace_with_ai_player__when_game_does_not_exist__should_not_raise(self, service):
        service.replace_with_ai_player("nonexistent", 0)


def _take_live_copy(live_tiles: list[int], man: str) -> int:
    tile_34 = tile_to_34(TilesConverter.string_to_136_array(man=man)[0])
    tile_id = next(t for t in live_tiles if tile_to_34(t) == tile_34)
    live_tiles.remove(tile_id)
    return tile_id


class TestMahjongGameServiceProcessAIPlayerActionsAfterReplacement:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_ai_actions_after_replacement__when_round_not_playing__should_return_no_events(self, service):
        service.start_game("game1", ["Alice"])
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        events = service.process_ai_player_actions_after_replacement("game1", seat=0).events
        assert events == []

    def test_ai_actions_after_replacement__when_replaced_player_has_turn__should_play_turn(self, service):
        service.start_game("game1", ["Alice"])
        game_state = service._runtimes["game1"].state
        round_state = game_state.round_state
        player = _find_player(round_state, "Alice")
        player_seat = player.seat

        player_tiles = list(player.tiles)
        live_tiles = list(round_state.wall.live_tiles)
        while len(player_tiles) < 14:
            if live_tiles:
                player_tiles.append(live_tiles.pop())

        new_players = []
        for p in round_state.players:
            if p.seat == player_seat:
                new_players.append(p.model_copy(update={"tiles": tuple(player_tiles)}))
            elif len(p.tiles) > 13:
                new_players.append(p.model_copy(update={"tiles": tuple(list(p.tiles)[:13])}))
            else:
                new_players.append(p)

        new_wall = round_state.wall.model_copy(update={"live_tiles": tuple(live_tiles)})
        _update_round_state(
            service,
            "game1",
            current_player_seat=player_seat,
            wall=new_wall,
            players=tuple(new_players),
            pending_call_prompt=None,
        )

        service.replace_with_ai_player("game1", player_seat)
        events = service.process_ai_player_actions_after_replacement("game1", player_seat).events
        assert events[0].data == DiscardEvent(seat=player_seat, tile_id=player_tiles[-1], is_tsumogiri=True)

    def test_ai_actions_after_replacement__when_replaced_right_after_own_chi__should_discard_legally(
        self, service, caplog
    ):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        round_state = service._runtimes["game1"].state.round_state
        alice = _find_player(round_state, "Alice")
        kamicha_seat = (alice.seat - 1) % 4
        live_tiles = list(round_state.wall.live_tiles)
        called_4m, held_4m, chi_5m, chi_6m, held_7m = (
            _take_live_copy(live_tiles, man=man) for man in ("4", "4", "5", "6", "7")
        )
        chi_meld = FrozenMeld(
            meld_type=FrozenMeld.CHI,
            tiles=(called_4m, chi_5m, chi_6m),
            opened=True,
            called_tile=called_4m,
            who=alice.seat,
            from_who=kamicha_seat,
        )
        hand_after_chi_of_4m_with_5m_6m = (*alice.tiles[:9], held_4m, held_7m)
        chi_kuikae = (tile_to_34(called_4m), tile_to_34(held_7m))
        _update_player(
            service,
            game_id="game1",
            seat=alice.seat,
            tiles=hand_after_chi_of_4m_with_5m_6m,
            melds=(chi_meld,),
            kuikae_tiles=chi_kuikae,
        )
        _update_round_state(
            service,
            "game1",
            wall=round_state.wall.model_copy(update={"live_tiles": tuple(live_tiles)}),
            current_player_seat=alice.seat,
            is_after_meld_call=True,
        )

        service.replace_with_ai_player("game1", alice.seat)
        events = service.process_ai_player_actions_after_replacement("game1", alice.seat).events
        discard = events[0].data
        assert isinstance(discard, DiscardEvent)
        assert discard.seat == alice.seat
        assert tile_to_34(discard.tile_id) not in chi_kuikae
        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []

    def test_ai_actions_after_replacement__when_replaced_player_is_pending_caller__should_clear_their_seat(
        self, service
    ):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        game_state = service._runtimes["game1"].state
        round_state = game_state.round_state
        alice = _find_player(round_state, "Alice")

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 1) % 4,
            pending_seats=frozenset({alice.seat}),
            callers=(Caller(seat=alice.seat, can_ron=True),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        service.replace_with_ai_player("game1", alice.seat)
        service.process_ai_player_actions_after_replacement("game1", alice.seat)
        updated_round = service._runtimes["game1"].state.round_state
        assert updated_round.pending_call_prompt is None

    def test_ai_actions_after_replacement__when_other_player_still_pending__should_keep_prompt_for_them(self, service):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._runtimes["game1"].state
        round_state = game_state.round_state
        alice = _find_player(round_state, "Alice")
        bob = _find_player(round_state, "Bob")

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 2) % 4,
            pending_seats=frozenset({alice.seat, bob.seat}),
            callers=(Caller(seat=alice.seat, can_ron=True), Caller(seat=bob.seat, can_ron=True)),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)
        waiting = service.get_awaiting("game1")

        service.replace_with_ai_player("game1", alice.seat)
        update = service.process_ai_player_actions_after_replacement("game1", alice.seat)
        events = update.events
        assert update.awaiting == replace(waiting, seats=frozenset({bob.seat}))
        updated_round = service._runtimes["game1"].state.round_state
        assert updated_round.pending_call_prompt is not None
        assert bob.seat in updated_round.pending_call_prompt.pending_seats
        assert alice.seat not in updated_round.pending_call_prompt.pending_seats
        assert [(e.event, e.target, e.data.is_furiten) for e in events if e.event == EventType.FURITEN] == [
            (EventType.FURITEN, SeatTarget(seat=alice.seat), True),
        ]

    def test_ai_actions_after_replacement__when_prompt_resolution_ends_round__should_emit_round_end(self, service):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._runtimes["game1"].state
        round_state = game_state.round_state
        alice = _find_player(round_state, "Alice")

        discarder_seat = (alice.seat + 1) % 4
        tile_id = round_state.players[discarder_seat].tiles[0] if round_state.players[discarder_seat].tiles else 0
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=tile_id,
            from_seat=discarder_seat,
            pending_seats=frozenset({alice.seat}),
            callers=(Caller(seat=alice.seat, can_ron=True),),
        )
        _update_round_state(service, "game1", wall=Wall(), pending_call_prompt=prompt)

        service.replace_with_ai_player("game1", alice.seat)
        events = service.process_ai_player_actions_after_replacement("game1", alice.seat).events
        round_end_events = [e for e in events if e.event == EventType.ROUND_END]
        assert len(round_end_events) == 1


class TestAwaiting:
    def test_awaiting__when_closed_kan_draws_a_replacement__should_open_a_new_wait_for_the_same_seat(self):
        service = MahjongGameService()
        seat = service.start_game("game1", ["Alice"], seed="a" * 192).seats[0]
        hand = TilesConverter.string_to_136_array(man="1111", pin="234567", sou="2345")
        _update_player(service, game_id="game1", seat=seat, tiles=tuple(hand))
        waiting = service.get_awaiting("game1")
        assert (waiting.kind, waiting.seats) == (WaitKind.TURN, frozenset({seat}))

        update = service.handle_action(
            game_id="game1",
            seat=seat,
            action=GameAction.CALL_KAN,
            data={"tile_id": hand[0], "kan_type": KanType.CLOSED},
        )
        assert [e.event for e in update.events if e.event == EventType.DRAW] == [EventType.DRAW]
        assert update.awaiting == replace(waiting, wait_id=waiting.wait_id + 1)


class TestSeedDeterminism:
    def test_start_game__when_same_seed__should_deal_identical_games(self):
        service1 = MahjongGameService()
        service2 = MahjongGameService()

        service1.start_game("game1", ["Player"], seed="b" * 192)
        service2.start_game("game2", ["Player"], seed="b" * 192)

        state1 = service1._runtimes["game1"].state
        state2 = service2._runtimes["game2"].state
        names1 = [p.name for p in state1.round_state.players]
        names2 = [p.name for p in state2.round_state.players]
        assert names1 == names2
        tiles1 = [p.tiles for p in state1.round_state.players]
        tiles2 = [p.tiles for p in state2.round_state.players]
        assert tiles1 == tiles2
        assert state1.round_state.wall == state2.round_state.wall


class TestServiceAccessors:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_is_round_advance_pending__when_round_ended__should_return_true(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        service._handle_round_end(service._runtimes["game1"], result)
        assert service.is_round_advance_pending("game1") is True

    def test_get_pending_round_advance_seats__when_round_ended__should_list_all_seats(
        self,
    ):
        service = MahjongGameService()
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        service._handle_round_end(service._runtimes["game1"], result)

        assert service.get_pending_round_advance_seats("game1") == [0, 1, 2, 3]


class TestMahjongGameServiceInvalidStart:
    def test_start_game__when_settings_unsupported__should_raise_and_register_no_game(self):
        service = MahjongGameService()

        with pytest.raises(UnsupportedSettingsError, match="has_agariyame"):
            service.start_game("game1", ["Alice"], settings=GameSettings(has_agariyame=True))
        assert service.get_game_state("game1") is None


class TestServiceGuardClauses:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_get_game_seed__when_game_does_not_exist__should_return_none(self, service):
        assert service.get_game_seed("nonexistent") is None

    def test_get_pending_round_advance_seats__when_no_advance_pending__should_return_empty(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        assert service.get_pending_round_advance_seats("game1") == []


class TestMahjongGameServiceRestoreHumanPlayer:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_restore_human_player__when_seat_was_replaced__should_remove_ai_player_from_seat(self, service):
        service.start_game("game1", ["Alice"], seed="a" * 192)
        player = _find_player(service._runtimes["game1"].state.round_state, "Alice")
        seat = player.seat

        service.replace_with_ai_player("game1", seat)
        assert service._runtimes["game1"].ai.is_ai_player(seat) is True

        service.restore_human_player("game1", seat)
        assert service._runtimes["game1"].ai.is_ai_player(seat) is False

    def test_restore_human_player__when_game_does_not_exist__should_not_raise(self, service):
        service.restore_human_player("nonexistent", 0)


class TestMahjongGameServiceBuildReconnectionSnapshot:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_build_reconnection_snapshot__when_game_running__should_contain_full_game_state(self, service):
        service.start_game("game1", ["Alice"], seed="a" * 192)
        game_state = service._runtimes["game1"].state
        player = _find_player(game_state.round_state, "Alice")

        snapshot = service.build_reconnection_snapshot("game1", player.seat)
        assert snapshot is not None
        assert snapshot.my_tiles == list(player.tiles)
        assert len(snapshot.player_states) == 4
        assert len(snapshot.players) == 4
        assert snapshot.dora_indicators == list(game_state.round_state.wall.dora_indicators)
        assert snapshot.tiles_remaining == len(game_state.round_state.wall.live_tiles)
        for ps in snapshot.player_states:
            game_player = game_state.round_state.players[ps.seat]
            assert ps.score == game_player.score

    def test_build_reconnection_snapshot__when_human_restored__should_mark_player_as_not_ai(self, service):
        service.start_game("game1", ["Alice"], seed="a" * 192)
        player = _find_player(service._runtimes["game1"].state.round_state, "Alice")
        seat = player.seat

        service.replace_with_ai_player("game1", seat)
        service.restore_human_player("game1", seat)

        snapshot = service.build_reconnection_snapshot("game1", seat)
        assert snapshot is not None
        reconnected_player = next(p for p in snapshot.players if p.seat == seat)
        assert reconnected_player.is_ai_player is False

    def test_build_reconnection_snapshot__when_seat_in_temporary_furiten__should_report_its_furiten(self, service):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        alice = _find_player(service._runtimes["game1"].state.round_state, "Alice")
        bob = _find_player(service._runtimes["game1"].state.round_state, "Bob")
        _update_player(service, game_id="game1", seat=alice.seat, is_temporary_furiten=True)

        assert service.build_reconnection_snapshot("game1", alice.seat).is_furiten is True
        assert service.build_reconnection_snapshot("game1", bob.seat).is_furiten is False

    def test_build_reconnection_snapshot__when_game_does_not_exist__should_return_none(self, service):
        assert service.build_reconnection_snapshot("nonexistent", 0) is None


class TestMahjongGameServiceBuildDrawEventForSeat:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_build_draw_event_for_seat__when_seat_is_current_player__should_return_draw_event(self, service):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        game_state = service._runtimes["game1"].state
        current_seat = game_state.round_state.current_player_seat

        events = service.build_draw_event_for_seat("game1", current_seat)
        assert len(events) == 1
        assert events[0].event == EventType.DRAW
        assert isinstance(events[0].target, SeatTarget)
        assert events[0].target.seat == current_seat

    def test_build_draw_event_for_seat__when_dealer_holds_nine_terminals_on_first_draw__should_offer_kyuushu(
        self, service
    ):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        dealer_seat = service._runtimes["game1"].state.round_state.dealer_seat
        nine_terminal_types_hand = tuple(
            TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123")
            + TilesConverter.string_to_136_array(man="22334"),
        )
        _update_player(service, game_id="game1", seat=dealer_seat, tiles=nine_terminal_types_hand)

        events = service.build_draw_event_for_seat("game1", dealer_seat)
        assert [a.action for a in events[0].data.available_actions] == [PlayerAction.KYUUSHU]

    def test_build_draw_event_for_seat__when_right_after_own_call__should_return_empty(self, service):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        current_seat = service._runtimes["game1"].state.round_state.current_player_seat
        _update_round_state(service, "game1", is_after_meld_call=True)

        assert service.build_draw_event_for_seat("game1", current_seat) == []

    def test_build_draw_event_for_seat__when_seat_is_not_current_player__should_return_empty(self, service):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        game_state = service._runtimes["game1"].state
        other_seat = (game_state.round_state.current_player_seat + 1) % 4

        events = service.build_draw_event_for_seat("game1", other_seat)
        assert events == []

    def test_build_draw_event_for_seat__when_player_has_no_tiles__should_return_empty(self, service):
        service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        game_state = service._runtimes["game1"].state
        current_seat = game_state.round_state.current_player_seat
        _update_player(service, game_id="game1", seat=current_seat, tiles=())

        events = service.build_draw_event_for_seat("game1", current_seat)
        assert events == []

    def test_build_draw_event_for_seat__when_game_does_not_exist__should_return_empty(self, service):
        events = service.build_draw_event_for_seat("nonexistent", 0)
        assert events == []
