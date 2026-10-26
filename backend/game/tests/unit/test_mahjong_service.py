import logging
from dataclasses import replace

import pytest
from mahjong.tile import TilesConverter

from game.logic.action_result import ActionResult
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import (
    GameAction,
    KanType,
    MeldCallType,
    PlayerAction,
    PromptKind,
    RoundPhase,
    TimeoutType,
    WaitKind,
)
from game.logic.events import (
    DiscardEvent,
    EventType,
    SeatTarget,
)
from game.logic.exceptions import UnsupportedSettingsError
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.runtime import GameRuntime
from game.logic.settings import GameSettings
from game.logic.state import Caller, MeldOption, PendingCallPrompt
from game.logic.tiles import NUM_TILES, tile_to_34
from game.logic.turn import process_draw_phase
from game.logic.types import (
    ExhaustiveDrawResult,
    TenpaiHand,
)
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import make_start_wall, make_wall
from game.tests.unit.helpers import (
    _find_player,
    _string_to_34_tile,
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
        start = service.start_game("game1", ["Alice"])
        runtime = start.runtime
        player_seat = start.seats[0]
        ai_player_controller = runtime.ai
        assert ai_player_controller.is_ai_player(player_seat) is False

        service.replace_with_ai_player(runtime, player_seat)
        assert ai_player_controller.is_ai_player(player_seat) is True


def _take_live_copy(live_tiles: list[int], man: str) -> int:
    tile_34 = tile_to_34(TilesConverter.string_to_136_array(man=man)[0])
    tile_id = next(t for t in live_tiles if tile_to_34(t) == tile_34)
    live_tiles.remove(tile_id)
    return tile_id


def _discard_chun_to_two_ron_callers(service: MahjongGameService) -> tuple[GameRuntime, int]:
    chun_discard = tile_copies(2, honors="7")[0]
    players = (
        create_player(
            seat=0,
            tiles=(
                chun_discard,
                *tile_copies(0, honors="123456"),
                *tile_copies(1, honors="123456"),
                *tile_copies(1, man="1"),
            ),
        ),
        create_player(seat=1, tiles=tile_copies(0, man="123456789", sou="444", honors="7")),
        create_player(seat=2, tiles=(*tile_copies(0, pin="123456789", sou="555"), *tile_copies(1, honors="7"))),
        create_player(
            seat=3, tiles=(*tile_copies(2, honors="123456"), *tile_copies(3, honors="123456"), *tile_copies(2, man="1"))
        ),
    )
    game_state = create_dealt_game_state(players, seed="a" * 192)
    runtime = GameRuntime(game_id="game1", state=game_state, ai=AIPlayerController({}))
    service.handle_action(runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": chun_discard})
    prompt = runtime.state.round_state.pending_call_prompt
    assert prompt is not None
    assert prompt.callers == (Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True))
    return runtime, chun_discard


class TestMahjongGameServiceProcessAIPlayerActionsAfterReplacement:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_ai_actions_after_replacement__when_round_not_playing__should_return_no_events(self, service):
        runtime = service.start_game("game1", ["Alice"]).runtime
        _update_round_state(runtime, phase=RoundPhase.FINISHED)

        events = service.process_ai_player_actions_after_replacement(runtime, seat=0).events
        assert events == []

    def test_ai_actions_after_replacement__when_replaced_player_has_turn__should_play_turn(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob"]).runtime
        game_state = runtime.state
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
            runtime,
            current_player_seat=player_seat,
            wall=new_wall,
            players=tuple(new_players),
            pending_call_prompt=None,
        )

        service.replace_with_ai_player(runtime, player_seat)
        events = service.process_ai_player_actions_after_replacement(runtime, player_seat).events
        assert events[0].data == DiscardEvent(seat=player_seat, tile_id=player_tiles[-1], is_tsumogiri=True)

    def test_ai_actions_after_replacement__when_replaced_right_after_own_chi__should_discard_legally(
        self, service, caplog
    ):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        round_state = runtime.state.round_state
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
            runtime,
            seat=alice.seat,
            tiles=hand_after_chi_of_4m_with_5m_6m,
            melds=(chi_meld,),
            kuikae_tiles=chi_kuikae,
        )
        _update_round_state(
            runtime,
            wall=round_state.wall.model_copy(update={"live_tiles": tuple(live_tiles)}),
            current_player_seat=alice.seat,
            is_after_meld_call=True,
        )

        service.replace_with_ai_player(runtime, alice.seat)
        events = service.process_ai_player_actions_after_replacement(runtime, alice.seat).events
        discard = events[0].data
        assert isinstance(discard, DiscardEvent)
        assert discard.seat == alice.seat
        assert tile_to_34(discard.tile_id) not in chi_kuikae
        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []

    def test_ai_actions_after_replacement__when_replaced_player_is_pending_caller__should_answer_and_play_its_turn(
        self, service
    ):
        chun_discard = tile_copies(1, honors="7")[0]
        players = (
            create_player(
                seat=0,
                tiles=(chun_discard, *tile_copies(0, sou="123456789"), *tile_copies(1, honors="1234")),
            ),
            create_player(seat=1, tiles=tile_copies(0, man="123456789", pin="444", honors="7")),
            create_player(seat=2, tiles=(*tile_copies(1, sou="123456789"), *tile_copies(2, honors="1234"))),
            create_player(seat=3, tiles=(*tile_copies(2, sou="123456789"), *tile_copies(3, honors="1234"))),
        )
        runtime = GameRuntime(game_id="game1", state=create_dealt_game_state(players), ai=AIPlayerController({}))
        service.handle_action(runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": chun_discard})
        prompt = runtime.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (Caller(seat=1, can_ron=True),)

        service.replace_with_ai_player(runtime, 1)
        events = service.process_ai_player_actions_after_replacement(runtime, 1).events
        assert runtime.state.round_state.pending_call_prompt is None
        assert [e.data.seat for e in events if isinstance(e.data, DiscardEvent)] == [1]
        assert runtime.state.round_state.current_player_seat == 2

    def test_ai_actions_after_replacement__when_other_player_still_pending__should_keep_prompt_for_them(self, service):
        runtime, _ = _discard_chun_to_two_ron_callers(service)
        waiting = service.get_awaiting(runtime)
        assert (waiting.kind, waiting.seats) == (WaitKind.CALL, frozenset({1, 2}))

        service.replace_with_ai_player(runtime, 1)
        update = service.process_ai_player_actions_after_replacement(runtime, 1)
        assert update.awaiting == replace(waiting, seats=frozenset({2}))
        prompt = runtime.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.pending_seats == frozenset({2})
        assert [(e.target, e.data.is_furiten) for e in update.events if e.event == EventType.FURITEN] == [
            (SeatTarget(seat=1), True),
        ]

    def test_ai_actions_after_replacement__when_prompt_resolution_ends_round__should_handle_round_end(self, service):
        runtime, chun_discard = _discard_chun_to_two_ron_callers(service)
        service.handle_action(runtime, seat=2, action=GameAction.CALL_RON, data={})
        assert runtime.state.round_state.pending_call_prompt is not None

        service.replace_with_ai_player(runtime, 1)
        update = service.process_ai_player_actions_after_replacement(runtime, 1)
        round_ends = [e.data.result for e in update.events if e.event == EventType.ROUND_END]
        assert [(r.winner_seat, r.loser_seat, r.winning_tile) for r in round_ends] == [(2, 0, chun_discard)]
        assert (update.awaiting.kind, update.awaiting.seats) == (WaitKind.ROUND_ADVANCE, frozenset({0, 2, 3}))
        assert (runtime.state.round_number, runtime.state.round_state.dealer_seat) == (1, 1)

        for seat in (0, 2, 3):
            service.handle_action(runtime, seat=seat, action=GameAction.CONFIRM_ROUND, data={})
        assert runtime.state.round_state.phase == RoundPhase.PLAYING
        assert runtime.state.round_state.result is None


class TestAwaiting:
    def test_awaiting__when_closed_kan_draws_a_replacement__should_open_a_new_wait_for_the_same_seat(self):
        service = MahjongGameService()
        start = service.start_game("game1", ["Alice"], seed="a" * 192)
        runtime = start.runtime
        seat = start.seats[0]
        hand = TilesConverter.string_to_136_array(man="1111", pin="234567", sou="2345")
        _update_player(runtime, seat=seat, tiles=tuple(hand))
        waiting = service.get_awaiting(runtime)
        assert (waiting.kind, waiting.seats) == (WaitKind.TURN, frozenset({seat}))

        update = service.handle_action(
            runtime,
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

        runtime = service1.start_game("game1", ["Player"], seed="b" * 192).runtime
        runtime2 = service2.start_game("game2", ["Player"], seed="b" * 192).runtime

        state1 = runtime.state
        state2 = runtime2.state
        names1 = [p.name for p in state1.round_state.players]
        names2 = [p.name for p in state2.round_state.players]
        assert names1 == names2
        tiles1 = [p.tiles for p in state1.round_state.players]
        tiles2 = [p.tiles for p in state2.round_state.players]
        assert tiles1 == tiles2
        assert state1.round_state.wall == state2.round_state.wall


class TestRoundEndAwaiting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_get_awaiting__when_round_ended_with_four_humans__should_await_every_seat_confirmation(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"]).runtime

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        service._handle_round_end(runtime, result)

        awaiting = service.get_awaiting(runtime)
        assert (awaiting.kind, awaiting.seats) == (WaitKind.ROUND_ADVANCE, frozenset({0, 1, 2, 3}))


class TestMahjongGameServiceInvalidStart:
    def test_start_game__when_settings_unsupported__should_raise(self):
        service = MahjongGameService()

        with pytest.raises(UnsupportedSettingsError, match="has_agariyame"):
            service.start_game("game1", ["Alice"], settings=GameSettings(has_agariyame=True))


class TestMahjongGameServiceRestoreHumanPlayer:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_restore_human_player__when_seat_was_replaced__should_remove_ai_player_from_seat(self, service):
        runtime = service.start_game("game1", ["Alice"], seed="a" * 192).runtime
        player = _find_player(runtime.state.round_state, "Alice")
        seat = player.seat

        service.replace_with_ai_player(runtime, seat)
        assert runtime.ai.is_ai_player(seat) is True

        service.restore_human_player(runtime, seat)
        assert runtime.ai.is_ai_player(seat) is False


class TestMahjongGameServiceBuildReconnectionSnapshot:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_build_reconnection_snapshot__when_game_running__should_contain_full_game_state(self, service):
        runtime = service.start_game("game1", ["Alice"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Alice")

        snapshot = service.build_reconnection_snapshot(runtime, player.seat)
        assert snapshot is not None
        assert snapshot.my_tiles == list(player.tiles)
        assert len(snapshot.player_states) == 4
        assert len(snapshot.players) == 4
        assert snapshot.dora_indicators == list(game_state.round_state.wall.dora_indicators)
        assert snapshot.tiles_remaining == len(game_state.round_state.wall.live_tiles)
        for ps in snapshot.player_states:
            game_player = game_state.round_state.players[ps.seat]
            assert ps.score == game_player.score

        dealer_seat = game_state.round_state.dealer_seat
        assert [ps.tile_count for ps in snapshot.player_states] == [
            14 if seat == dealer_seat else 13 for seat in range(4)
        ]

    def test_build_reconnection_snapshot__when_human_restored__should_mark_player_as_not_ai(self, service):
        runtime = service.start_game("game1", ["Alice"], seed="a" * 192).runtime
        player = _find_player(runtime.state.round_state, "Alice")
        seat = player.seat

        service.replace_with_ai_player(runtime, seat)
        service.restore_human_player(runtime, seat)

        snapshot = service.build_reconnection_snapshot(runtime, seat)
        assert snapshot is not None
        reconnected_player = next(p for p in snapshot.players if p.seat == seat)
        assert reconnected_player.is_ai_player is False

    def test_build_reconnection_snapshot__when_round_ended_before__should_list_it_with_its_own_dealer_and_honba(
        self, service
    ):
        runtime = service.start_game("game1", ["Alice"], seed="a" * 192).runtime
        alice = _find_player(runtime.state.round_state, "Alice")
        riichi_seat = (alice.seat + 1) % 4
        first_dealer = runtime.state.round_state.dealer_seat
        tenpai_hand = TilesConverter.string_to_136_array(man="123456789", pin="11", sou="45")
        _update_player(runtime, seat=riichi_seat, tiles=tuple(tenpai_hand), is_riichi=True)
        _update_round_state(runtime, wall=make_wall())
        exhausted_game, draw_events = process_draw_phase(runtime.state)
        runtime.commit(exhausted_game)
        service._process_action_result_internal(runtime, ActionResult(draw_events, state=exhausted_game))
        service.handle_timeout(runtime, seat=alice.seat, timeout_type=TimeoutType.ROUND_ADVANCE)
        assert runtime.state.round_number == 1

        payload = service.build_reconnection_snapshot(runtime, alice.seat).model_dump(by_alias=True, exclude_none=True)
        assert payload["h"] == 1
        assert payload["rh"] == [
            {
                "w": 0,
                "dl": first_dealer,
                "h": 0,
                "rs": (riichi_seat,),
                "ws": (),
                "ts": (riichi_seat,),
                "sch": {seat: 30 if seat == riichi_seat else -10 for seat in range(4)},
            },
        ]

    def test_build_reconnection_snapshot__when_round_advance_pending__should_show_the_ended_round_with_its_result(
        self, service
    ):
        runtime = service.start_game("game1", ["Alice"], seed="a" * 192).runtime
        alice = _find_player(runtime.state.round_state, "Alice")
        first_dealer = runtime.state.round_state.dealer_seat
        tenpai_seat = (first_dealer + 1) % 4
        tenpai_hand = TilesConverter.string_to_136_array(man="123456789", pin="11", sou="45")
        _update_player(runtime, seat=tenpai_seat, tiles=tuple(tenpai_hand))
        _update_round_state(runtime, wall=make_wall())
        exhausted_game, draw_events = process_draw_phase(runtime.state)
        runtime.commit(exhausted_game)
        service._process_action_result_internal(runtime, ActionResult(draw_events, state=exhausted_game))
        assert service.get_awaiting(runtime).kind == WaitKind.ROUND_ADVANCE
        assert (runtime.state.round_state.dealer_seat, runtime.state.round_number, runtime.state.honba_sticks) == (
            tenpai_seat,
            1,
            1,
        )

        snapshot = service.build_reconnection_snapshot(runtime, alice.seat)
        payload = snapshot.model_dump(by_alias=True, exclude_none=True)
        assert (payload["dl"], payload["w"], payload["n"], payload["h"]) == (first_dealer, 0, 0, 0)
        assert isinstance(snapshot.result, ExhaustiveDrawResult)
        assert snapshot.result.tempai_seats == [tenpai_seat]
        assert {ps["s"]: ps["sc"] for ps in payload["pst"]} == {
            seat: 280 if seat == tenpai_seat else 240 for seat in range(4)
        }

    def test_build_reconnection_snapshot__when_round_advance_follows_a_robbed_kan__should_name_the_robbed_kan(
        self, service
    ):
        man_1 = [tile_copies(copy, man="1")[0] for copy in range(4)]
        kokushi_on_man_1 = (*tile_copies(0, man="9", pin="19", sou="19", honors="1234567"), *tile_copies(3, man="9"))
        others = [tile for tile in range(NUM_TILES) if tile not in {*man_1, *kokushi_on_man_1}]
        dealer_hand = (*man_1[:3], *others[:10])
        wall = make_start_wall((dealer_hand, kokushi_on_man_1, others[10:23], others[23:36]), draws=(man_1[3],))

        runtime = service.start_game(
            "game1",
            ["Alice", "Bob", "Charlie", "Diana"],
            seed="a" * 192,
            settings=GameSettings(tobi_enabled=False),
            wall=list(wall),
        ).runtime
        service.handle_action(
            runtime, seat=0, action=GameAction.CALL_KAN, data={"tile_id": man_1[3], "kan_type": "closed"}
        )
        service.handle_action(runtime, seat=1, action=GameAction.CALL_RON, data={})
        assert service.get_awaiting(runtime).kind == WaitKind.ROUND_ADVANCE

        payload = service.build_reconnection_snapshot(runtime, 2).model_dump(by_alias=True, exclude_none=True)
        assert payload["re"]["rk"] == {"s": 0, "ti": man_1[3], "kty": "closed"}


class TestMahjongGameServiceBuildWaitEventsForSeat:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_build_wait_events_for_seat__when_seat_is_current_player__should_return_draw_event(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        game_state = runtime.state
        current_seat = game_state.round_state.current_player_seat

        events = service.build_wait_events_for_seat(runtime, current_seat)
        assert len(events) == 1
        assert events[0].event == EventType.DRAW
        assert isinstance(events[0].target, SeatTarget)
        assert events[0].target.seat == current_seat

    def test_build_wait_events_for_seat__when_dealer_holds_nine_terminals_on_first_draw__should_offer_kyuushu(
        self, service
    ):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        dealer_seat = runtime.state.round_state.dealer_seat
        nine_terminal_types_hand = tuple(
            TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123")
            + TilesConverter.string_to_136_array(man="22334"),
        )
        _update_player(runtime, seat=dealer_seat, tiles=nine_terminal_types_hand)

        events = service.build_wait_events_for_seat(runtime, dealer_seat)
        assert [a.action for a in events[0].data.available_actions] == [PlayerAction.KYUUSHU]

    def test_build_wait_events_for_seat__when_right_after_own_call__should_return_turn_event_with_kuikae(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        current_seat = runtime.state.round_state.current_player_seat
        kuikae_type = _string_to_34_tile(man="5")
        _update_player(runtime, seat=current_seat, kuikae_tiles=(kuikae_type,))
        _update_round_state(runtime, is_after_meld_call=True)

        events = service.build_wait_events_for_seat(runtime, current_seat)
        assert [e.event for e in events] == [EventType.TURN]
        assert events[0].target == SeatTarget(seat=current_seat)
        assert events[0].data.kuikae_tiles == [kuikae_type]

    def test_build_wait_events_for_seat__when_seat_is_not_current_player__should_return_empty(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        game_state = runtime.state
        other_seat = (game_state.round_state.current_player_seat + 1) % 4

        events = service.build_wait_events_for_seat(runtime, other_seat)
        assert events == []

    def test_build_wait_events_for_seat__when_a_call_prompt_awaits_the_seat__should_return_its_prompt_not_a_draw(
        self, service
    ):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        discarder = runtime.state.round_state.current_player_seat
        ron_seat, pon_seat = (discarder + 1) % 4, (discarder + 2) % 4
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=runtime.state.round_state.players[discarder].tiles[0],
            from_seat=discarder,
            pending_seats=frozenset({pon_seat}),
            callers=(
                Caller(seat=ron_seat, can_ron=True),
                Caller(seat=pon_seat, melds=(MeldOption(call_type=MeldCallType.PON),)),
            ),
        )
        _update_round_state(runtime, pending_call_prompt=prompt)

        events = service.build_wait_events_for_seat(runtime, pon_seat)
        assert [(e.event, e.target) for e in events] == [(EventType.CALL_PROMPT, SeatTarget(seat=pon_seat))]
        assert service.build_wait_events_for_seat(runtime, ron_seat) == []
        assert service.build_wait_events_for_seat(runtime, discarder) == []

    def test_build_wait_events_for_seat__when_the_round_advance_is_pending__should_return_empty(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        current_seat = runtime.state.round_state.current_player_seat
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))
        drawn_tile = runtime.state.round_state.players[current_seat].tiles[-1]
        service.handle_action(runtime, seat=current_seat, action=GameAction.DISCARD, data={"tile_id": drawn_tile})
        assert service.get_awaiting(runtime).kind == WaitKind.ROUND_ADVANCE

        assert service.build_wait_events_for_seat(runtime, current_seat) == []

    def test_build_wait_events_for_seat__when_player_has_no_tiles__should_return_empty(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192).runtime
        game_state = runtime.state
        current_seat = game_state.round_state.current_player_seat
        _update_player(runtime, seat=current_seat, tiles=())

        events = service.build_wait_events_for_seat(runtime, current_seat)
        assert events == []
