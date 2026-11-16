import pytest
from mahjong.tile import TilesConverter

from game.logic.action_result import ActionResult
from game.logic.decision import Discard as DiscardAction
from game.logic.decision import Kan, Kyuushu, Pass, Pon, Ron
from game.logic.enums import (
    KanType,
    MeldCallType,
    PlayerAction,
    PromptKind,
    RoundPhase,
    RoundResultType,
    WindName,
)
from game.logic.events import (
    EventType,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
)
from game.logic.exceptions import DiscardHistoryError
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.refusal import Refusal
from game.logic.runtime import GameRuntime
from game.logic.service import Call, Dealt, GameOver, RoundOver, Turn
from game.logic.settings import GameSettings, GameType
from game.logic.state import Caller, Discard, MeldOption, PendingCallPrompt
from game.logic.tiles import NUM_TILES
from game.logic.turn import process_draw_phase
from game.logic.types import (
    ExhaustiveDrawResult,
    RobbedKan,
    RonResult,
    RoundHistoryEntry,
    StartPosition,
)
from game.logic.wall import create_wall, deal_initial_hands
from game.tests.helpers.builders import create_dealt_game_state, create_player, start_game_in_play
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.start_wall import make_start_wall
from game.tests.helpers.wall import make_wall
from game.tests.unit.logic.helpers import (
    _first_human,
    _string_to_34_tile,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceAllPlayers:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_new_game__when_four_players__should_emit_single_draw_event_for_dealer(self, service):
        events = start_game_in_play(service, seed="a" * 192).events
        # with 4 players, exactly 1 draw event for dealer (no AI player followup chain)
        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) == 1


class TestMahjongGameServiceBeginRound:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_new_game__when_started__should_stop_after_the_deal_until_begin_round_draws(self, service):
        runtime, events = service.new_game("c" * 192)
        assert [type(e) for e in events] == [GameStartedEvent] + [RoundStartedEvent] * 4
        assert service.get_awaiting(runtime) == Dealt()

        begun = service.begin_round(runtime)
        in_play = start_game_in_play(MahjongGameService(), seed="c" * 192)
        assert begun == in_play.events[len(events) :]
        assert service.get_awaiting(runtime) == Turn(seat=runtime.state.round_state.dealer_seat)
        assert runtime.state.round_state == in_play.runtime.state.round_state


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
    runtime = GameRuntime(state=game_state)
    service.act(runtime, 0, DiscardAction(tile=chun_discard))
    prompt = runtime.state.round_state.pending_call_prompt
    assert prompt is not None
    assert prompt.callers == (Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True))
    return runtime, chun_discard


class TestMahjongGameServiceCallAnswers:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_act__when_the_last_caller_passes_after_a_ron__should_end_the_round(self, service):
        runtime, chun_discard = _discard_chun_to_two_ron_callers(service)
        service.act(runtime, 2, Ron())
        assert service.get_awaiting(runtime) == Call(seats=frozenset({1}))

        events = service.act(runtime, 1, Pass())
        round_ends = [e.result for e in events if e.type == EventType.ROUND_END]
        assert [(r.winner_seat, r.loser_seat, r.winning_tile) for r in round_ends] == [(2, 0, chun_discard)]
        assert service.get_awaiting(runtime) == RoundOver()
        assert (runtime.state.round_number, runtime.state.round_state.dealer_seat) == (1, 1)

        service.deal_next_round(runtime)
        service.begin_round(runtime)
        assert runtime.state.round_state.phase == RoundPhase.PLAYING
        assert runtime.state.round_state.result is None


class TestSeedDeterminism:
    def test_new_game__when_same_seed__should_deal_identical_games(self):
        service1 = MahjongGameService()
        service2 = MahjongGameService()

        runtime = start_game_in_play(service1, humans=1, seed="b" * 192).runtime
        runtime2 = start_game_in_play(service2, humans=1, seed="b" * 192).runtime

        state1 = runtime.state
        state2 = runtime2.state
        tiles1 = [p.tiles for p in state1.round_state.players]
        tiles2 = [p.tiles for p in state2.round_state.players]
        assert tiles1 == tiles2
        assert state1.round_state.wall == state2.round_state.wall

    def test_new_game__when_given_two_walls_and_a_start__should_deal_from_the_start_each_wall_then_the_seed(self):
        seed = "b" * 192
        dealer = 2
        start = StartPosition(
            scores=(20000, 30000, 26000, 23000),
            honba_sticks=1,
            riichi_sticks=1,
            dealer_seat=dealer,
            round_wind=1,
            round_number=5,
        )
        dealer_hands = [tile_copies(copy, man="19", pin="19", sou="19", honors="1234567") for copy in (0, 1)]
        walls = [
            make_start_wall(
                [dealer_hand, *(tile_copies(copy, man="2345678", pin="234", sou="234") for copy in range(3))]
            )
            for dealer_hand in dealer_hands
        ]
        service = MahjongGameService()

        game_start = start_game_in_play(service, seed=seed, walls=walls, start=start)
        first_deal = [event for event in game_start.events if isinstance(event, RoundStartedEvent)]
        runtime = game_start.runtime
        (game_started,) = [event for event in game_start.events if isinstance(event, GameStartedEvent)]
        assert game_started.dealer_seat == 0
        assert [[player.score for player in event.players] for event in first_deal] == [list(start.scores)] * 4
        assert {
            (event.dealer_seat, event.round_wind, event.round_in_wind, event.honba_sticks, event.riichi_sticks)
            for event in first_deal
        } == {(dealer, WindName.SOUTH, 3, 1, 1)}
        assert sorted(first_deal[dealer].my_tiles) == sorted(dealer_hands[0])

        deals = []
        for _ in range(2):
            service.act(runtime, dealer, Kyuushu())
            dealt = service.deal_next_round(runtime)
            assert not isinstance(dealt, Refusal), dealt
            service.begin_round(runtime)
            deals.append([event for event in dealt if isinstance(event, RoundStartedEvent)])

        second_deal, third_deal = deals
        assert sorted(second_deal[dealer].my_tiles) == sorted(dealer_hands[1])
        assert second_deal[dealer].dice == (1, 1)
        seeded_wall, seeded_hands = deal_initial_hands(
            create_wall(seed=seed, round_number=7, dealer_seat=dealer), dealer
        )
        assert [event.my_tiles for event in third_deal] == seeded_hands
        assert {(event.round_number, event.dice) for event in third_deal} == {(7, seeded_wall.dice)}


class TestRoundEndAwaiting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    @pytest.mark.parametrize(
        ("unique_dealers", "tenpai_seat_after_dealer", "expected_wait"),
        [
            pytest.param(8, 0, GameOver(), id="south_4_dealer_stays_first_at_target"),
            pytest.param(7, 1, RoundOver(), id="south_3_next_dealer_first_at_target"),
        ],
    )
    def test_round_end__when_tenpai_seat_is_first_at_target__should_stop_only_for_a_staying_dealer(
        self, service, unique_dealers, tenpai_seat_after_dealer, expected_wait
    ):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        state = runtime.state
        dealer_seat = state.round_state.dealer_seat
        tenpai_seat = (dealer_seat + tenpai_seat_after_dealer) % 4
        players = tuple(
            player.model_copy(update={"score": 31000 if player.seat == tenpai_seat else 23000})
            for player in state.round_state.players
        )
        runtime.commit(
            state.model_copy(
                update={
                    "unique_dealers": unique_dealers,
                    "round_state": state.round_state.model_copy(update={"players": players}),
                }
            )
        )
        tenpai_hand = TilesConverter.string_to_136_array(man="123456789", pin="11", sou="45")
        dealer_discard = tile_copies(3, honors="7")[0]
        if tenpai_seat == dealer_seat:
            _update_player(runtime, seat=dealer_seat, tiles=(*tenpai_hand, dealer_discard))
        else:
            _update_player(runtime, seat=tenpai_seat, tiles=tuple(tenpai_hand))
            dealer_discard = runtime.state.round_state.players[dealer_seat].tiles[-1]

        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))
        events = service.act(runtime, dealer_seat, DiscardAction(tile=dealer_discard))
        (round_end,) = [event for event in events if event.type == EventType.ROUND_END]
        assert round_end.result.tempai_seats == [tenpai_seat]

        assert service.get_awaiting(runtime) == expected_wait


def _latest_discard_seat(service: MahjongGameService, runtime: GameRuntime) -> int | None:
    return service.build_reconnection_snapshot(runtime, 0).latest_discard_seat


def _discards(*tiles: int) -> tuple[Discard, ...]:
    return tuple(Discard(tile_id=tile) for tile in tiles)


class TestMahjongGameServiceBuildReconnectionSnapshot:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_build_reconnection_snapshot__when_game_running__should_contain_full_game_state(self, service):
        runtime = start_game_in_play(service, humans=1, seed="a" * 192).runtime
        runtime.commit(runtime.state.model_copy(update={"settings": GameSettings(game_type=GameType.TONPUSEN)}))
        game_state = runtime.state
        player = _first_human(game_state)

        snapshot = service.build_reconnection_snapshot(runtime, player.seat)
        assert snapshot is not None
        assert snapshot.game_type == GameType.TONPUSEN
        assert snapshot.my_tiles == list(player.tiles)
        assert len(snapshot.player_states) == 4
        assert snapshot.dora_indicators == list(game_state.round_state.wall.dora_indicators)
        assert snapshot.tiles_remaining == len(game_state.round_state.wall.live_tiles)
        assert (snapshot.round_in_wind, snapshot.first_dealer_seat) == (1, game_state.round_state.dealer_seat)
        for ps in snapshot.player_states:
            game_player = game_state.round_state.players[ps.seat]
            assert ps.score == game_player.score

        dealer_seat = game_state.round_state.dealer_seat
        assert [ps.tile_count for ps in snapshot.player_states] == [
            14 if seat == dealer_seat else 13 for seat in range(4)
        ]
        assert snapshot.latest_discard_seat is None

    def test_build_reconnection_snapshot__when_round_ended_before__should_list_it_with_its_own_dealer_and_honba(
        self, service
    ):
        runtime = start_game_in_play(service, humans=1, seed="a" * 192).runtime
        alice = _first_human(runtime.state)
        riichi_seat = (alice.seat + 1) % 4
        first_dealer = runtime.state.round_state.dealer_seat
        tenpai_hand = TilesConverter.string_to_136_array(man="123456789", pin="11", sou="45")
        _update_player(runtime, seat=riichi_seat, tiles=tuple(tenpai_hand), is_riichi=True)
        _update_round_state(runtime, wall=make_wall())
        exhausted_game, draw_events = process_draw_phase(runtime.state)
        service._commit_and_process(runtime, ActionResult(draw_events, state=exhausted_game))
        service.deal_next_round(runtime)
        service.begin_round(runtime)
        assert runtime.state.round_number == 1

        snapshot = service.build_reconnection_snapshot(runtime, alice.seat)
        assert snapshot.honba_sticks == 1
        assert snapshot.round_history == [
            RoundHistoryEntry(
                round_wind=WindName.EAST,
                round_in_wind=1,
                dealer_seat=first_dealer,
                honba_sticks=0,
                result_type=RoundResultType.EXHAUSTIVE_DRAW,
                riichi_seats=(riichi_seat,),
                winner_seats=(),
                pao_seats=(),
                tenpai_seats=(riichi_seat,),
                score_changes={seat: 3000 if seat == riichi_seat else -1000 for seat in range(4)},
            ),
        ]

    def test_build_reconnection_snapshot__when_round_is_over__should_show_the_ended_round_with_its_result(
        self, service
    ):
        runtime = start_game_in_play(service, humans=1, seed="a" * 192).runtime
        alice = _first_human(runtime.state)
        first_dealer = runtime.state.round_state.dealer_seat
        tenpai_seat = (first_dealer + 1) % 4
        tenpai_hand = TilesConverter.string_to_136_array(man="123456789", pin="11", sou="45")
        _update_player(runtime, seat=tenpai_seat, tiles=tuple(tenpai_hand))
        _update_round_state(runtime, wall=make_wall())
        exhausted_game, draw_events = process_draw_phase(runtime.state)
        service._commit_and_process(runtime, ActionResult(draw_events, state=exhausted_game))
        assert service.get_awaiting(runtime) == RoundOver()
        assert (runtime.state.round_state.dealer_seat, runtime.state.round_number, runtime.state.honba_sticks) == (
            tenpai_seat,
            1,
            1,
        )

        snapshot = service.build_reconnection_snapshot(runtime, alice.seat)
        assert (
            snapshot.dealer_seat,
            snapshot.round_wind,
            snapshot.round_number,
            snapshot.round_in_wind,
            snapshot.honba_sticks,
            snapshot.riichi_sticks,
        ) == (first_dealer, WindName.EAST, 0, 1, 0, 0)
        assert isinstance(snapshot.result, ExhaustiveDrawResult)
        assert snapshot.result.tempai_seats == [tenpai_seat]
        assert {ps.seat: ps.score for ps in snapshot.player_states} == {
            seat: 28000 if seat == tenpai_seat else 24000 for seat in range(4)
        }

    def test_build_reconnection_snapshot__when_round_over_follows_a_robbed_kan__should_name_the_robbed_kan(
        self, service
    ):
        man_1 = [tile_copies(copy, man="1")[0] for copy in range(4)]
        kokushi_on_man_1 = (*tile_copies(0, man="9", pin="19", sou="19", honors="1234567"), *tile_copies(3, man="9"))
        others = [tile for tile in range(NUM_TILES) if tile not in {*man_1, *kokushi_on_man_1}]
        dealer_hand = (*man_1[:3], *others[:10])
        wall = make_start_wall((dealer_hand, kokushi_on_man_1, others[10:23], others[23:36]), draws=(man_1[3],))

        runtime = start_game_in_play(
            service,
            seed="a" * 192,
            walls=[wall],
            start=StartPosition(scores=(50000, 20000, 15000, 15000)),
        ).runtime
        service.act(runtime, 0, Kan(kan_type=KanType.CLOSED, tile=man_1[3]))
        service.act(runtime, 1, Ron())
        assert service.get_awaiting(runtime) == RoundOver()

        snapshot = service.build_reconnection_snapshot(runtime, 2)
        assert isinstance(snapshot.result, RonResult)
        assert snapshot.result.robbed_kan == RobbedKan(seat=0, tile_id=man_1[3], kan_type=KanType.CLOSED)

    def test_build_reconnection_snapshot__when_the_latest_discard_is_claimed__should_name_no_latest_discard(
        self, service
    ):
        earlier_discard = tile_copies(2, honors="1")[0]
        haku = tile_copies(0, honors="5")[0]
        players = (
            create_player(
                seat=0,
                tiles=tile_copies(0, man="1479", pin="147", sou="147", honors="123"),
                discards=_discards(earlier_discard),
            ),
            create_player(seat=1, tiles=tile_copies(0, man="258", pin="2589", sou="2589", honors="567")),
            create_player(seat=2, tiles=tile_copies(1, man="258", pin="258", sou="1258", honors="123")),
            create_player(
                seat=3,
                tiles=(
                    *tile_copies(0, man="36", pin="36", sou="36"),
                    *tile_copies(1, man="147", pin="14", honors="5"),
                    tile_copies(2, honors="5")[0],
                ),
            ),
        )
        runtime = GameRuntime(
            state=create_dealt_game_state(players, current_player_seat=1, seed="a" * 192),
        )

        service.act(runtime, 1, DiscardAction(tile=haku))
        assert runtime.state.round_state.pending_call_prompt is not None
        offered = _latest_discard_seat(service, runtime)
        service.act(runtime, 3, Pon())

        assert (offered, _latest_discard_seat(service, runtime)) == (1, None)

    def test_build_reconnection_snapshot__when_the_next_seat_drew__should_name_no_latest_discard(self, service):
        man_1 = [tile_copies(copy, man="1")[0] for copy in range(4)]
        sou_5 = [tile_copies(copy, sou="5")[0] for copy in range(4)]
        latest_discard = tile_copies(2, man="9")[0]
        pon_from_seat_3 = FrozenMeld(
            tiles=tuple(sou_5[:3]),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=sou_5[0],
            who=1,
            from_who=3,
        )
        discards_by_seat = (
            [*tile_copies(0, honors="2"), latest_discard],
            tile_copies(0, honors="36"),
            tile_copies(0, honors="47"),
            [sou_5[0], tile_copies(1, honors="1")[0]],
        )
        players = (
            create_player(
                seat=0,
                tiles=(
                    *tile_copies(1, man="3467", pin="148", sou="289", honors="57"),
                    tile_copies(0, honors="5")[0],
                ),
                discards=_discards(*discards_by_seat[0]),
            ),
            create_player(
                seat=1,
                tiles=(*man_1, sou_5[3], *tile_copies(0, pin="289", sou="9"), *tile_copies(1, sou="1", honors="6")),
                melds=(pon_from_seat_3,),
                discards=_discards(*discards_by_seat[1]),
            ),
            create_player(
                seat=2,
                tiles=(*tile_copies(0, man="234567", pin="345", sou="634"), tile_copies(1, sou="6")[0]),
                discards=_discards(*discards_by_seat[2]),
            ),
            create_player(
                seat=3,
                tiles=(
                    *tile_copies(0, man="89", pin="17", sou="17"),
                    *tile_copies(2, honors="1234"),
                    *tile_copies(1, man="25", pin="6"),
                ),
                discards=_discards(*discards_by_seat[3]),
            ),
        )
        play_order = ((0, 0), (1, 0), (2, 0), (3, 0), (1, 1), (2, 1), (3, 1), (0, 1))
        all_discards = [discards_by_seat[seat][turn] for seat, turn in play_order]
        runtime = GameRuntime(
            state=create_dealt_game_state(
                players,
                current_player_seat=1,
                all_discards=all_discards,
                rinshan_draws=tile_copies(2, honors="7"),
                seed="a" * 192,
            ),
        )
        after_the_draw = _latest_discard_seat(service, runtime)

        service.act(runtime, 1, Kan(kan_type=KanType.CLOSED, tile=man_1[0]))
        assert len(runtime.state.round_state.players[1].melds) == 2
        after_the_closed_kan = _latest_discard_seat(service, runtime)
        service.act(runtime, 1, Kan(kan_type=KanType.ADDED, tile=sou_5[3]))
        assert runtime.state.round_state.pending_call_prompt is not None
        in_the_chankan_window = _latest_discard_seat(service, runtime)
        service.act(runtime, 2, Ron())
        assert runtime.state.round_state.result is not None

        assert (after_the_draw, after_the_closed_kan, in_the_chankan_window) == (None, None, None)
        assert _latest_discard_seat(service, runtime) is None

    def test_build_reconnection_snapshot__when_the_discard_history_disagrees_with_the_rivers__should_raise(
        self, service
    ):
        first, second = tile_copies(0, honors="12")
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="123456789", pin="1234"), discards=_discards(first, second)),
            create_player(seat=1, tiles=tile_copies(1, man="123456789", pin="12345")),
            create_player(seat=2, tiles=tile_copies(2, man="123456789", pin="1234")),
            create_player(seat=3, tiles=tile_copies(3, man="123456789", pin="1234")),
        )
        state = create_dealt_game_state(players, current_player_seat=1, all_discards=[second, first], seed="a" * 192)
        runtime = GameRuntime(state=state)

        with pytest.raises(DiscardHistoryError):
            service.build_reconnection_snapshot(runtime, 0)


class TestMahjongGameServiceBuildWaitEventsForSeat:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_build_wait_events_for_seat__when_seat_is_current_player__should_return_draw_event(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        game_state = runtime.state
        current_seat = game_state.round_state.current_player_seat

        events = service.build_wait_events_for_seat(runtime, current_seat)
        assert len(events) == 1
        assert events[0].type == EventType.DRAW
        assert isinstance(events[0].target, SeatTarget)
        assert events[0].target.seat == current_seat

    def test_build_wait_events_for_seat__when_dealer_holds_nine_terminals_on_first_draw__should_offer_kyuushu(
        self, service
    ):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        dealer_seat = runtime.state.round_state.dealer_seat
        nine_terminal_types_hand = tuple(
            TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123")
            + TilesConverter.string_to_136_array(man="22334"),
        )
        _update_player(runtime, seat=dealer_seat, tiles=nine_terminal_types_hand)

        events = service.build_wait_events_for_seat(runtime, dealer_seat)
        assert [a.action for a in events[0].available_actions] == [PlayerAction.KYUUSHU]
        assert service.legal_actions(runtime, dealer_seat)[-1] == Kyuushu()

    def test_build_wait_events_for_seat__when_right_after_own_call__should_return_turn_event_with_kuikae(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        current_seat = runtime.state.round_state.current_player_seat
        kuikae_type = _string_to_34_tile(man="5")
        _update_player(runtime, seat=current_seat, kuikae_tiles=(kuikae_type,))
        _update_round_state(runtime, is_after_meld_call=True)

        events = service.build_wait_events_for_seat(runtime, current_seat)
        assert [e.type for e in events] == [EventType.TURN]
        assert events[0].target == SeatTarget(seat=current_seat)
        assert events[0].kuikae_tiles == [kuikae_type]

    def test_build_wait_events_for_seat__when_seat_is_not_current_player__should_return_empty(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        game_state = runtime.state
        other_seat = (game_state.round_state.current_player_seat + 1) % 4

        events = service.build_wait_events_for_seat(runtime, other_seat)
        assert events == []

    def test_build_wait_events_for_seat__when_a_call_prompt_awaits_the_seat__should_return_its_prompt_not_a_draw(
        self, service
    ):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
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
        assert [(e.type, e.target) for e in events] == [(EventType.CALL_PROMPT, SeatTarget(seat=pon_seat))]
        assert service.build_wait_events_for_seat(runtime, ron_seat) == []
        assert service.build_wait_events_for_seat(runtime, discarder) == []

    def test_build_wait_events_for_seat__when_the_round_is_over__should_return_empty(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        current_seat = runtime.state.round_state.current_player_seat
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))
        drawn_tile = runtime.state.round_state.players[current_seat].tiles[-1]
        service.act(runtime, current_seat, DiscardAction(tile=drawn_tile))
        assert service.get_awaiting(runtime) == RoundOver()

        assert service.build_wait_events_for_seat(runtime, current_seat) == []

    def test_build_wait_events_for_seat__when_player_has_no_tiles__should_return_empty(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        game_state = runtime.state
        current_seat = game_state.round_state.current_player_seat
        _update_player(runtime, seat=current_seat, tiles=())

        events = service.build_wait_events_for_seat(runtime, current_seat)
        assert events == []
