from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_chi, handle_discard, handle_pass, handle_pon, handle_ron
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    CallType,
    GameAction,
    MeldCallType,
    PromptKind,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    CallPromptEvent,
    DrawEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    SeatTarget,
    TurnEvent,
)
from game.logic.state import (
    Caller,
    CallResponse,
    Discard,
    MeldOption,
    PendingCallPrompt,
)
from game.logic.state_utils import update_game_with_round
from game.logic.tiles import tile_to_34
from game.logic.turn import process_discard_phase
from game.logic.types import ChiActionData, DiscardActionData, MeldCaller, PonActionData
from game.logic.win import get_waiting_tiles
from game.tests.conftest import create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies


def _make_wall_and_dead_wall():
    wall = tuple(TilesConverter.string_to_136_array(man="5555"))
    dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
    return wall, dead_wall


class TestRonPlusMeldCallersRonWins:
    def test_discard_claim__when_dual_seat_calls_a_meld_and_another_seat_rons__should_resolve_ron(self):
        three_pin = tile_copies(2, pin="3")[0]
        one_pin, two_pin = tile_copies(0, pin="12")
        dealer_hand = (
            *tile_copies(0, honors="123467"),
            *tile_copies(1, honors="123467"),
            *tile_copies(2, honors="1"),
            three_pin,
        )
        man_ittsu_on_three_pin = (*tile_copies(0, man="123456789", pin="125"), *tile_copies(1, pin="5"))
        sou_ittsu_on_three_pin = (*tile_copies(0, sou="123456789", honors="5"), *tile_copies(1, pin="12", honors="5"))
        no_pin_hand = (*tile_copies(1, man="123456789"), *tile_copies(1, sou="1234"))
        players = (
            create_player(seat=0, tiles=dealer_hand),
            create_player(seat=1, tiles=man_ittsu_on_three_pin),
            create_player(seat=2, tiles=sou_ittsu_on_three_pin),
            create_player(seat=3, tiles=no_pin_hand),
        )
        round_state = create_round_state(
            players=players,
            wall=tile_copies(2, man="123456789"),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)
        assert get_waiting_tiles(players[1]) == get_waiting_tiles(players[2]) == {tile_to_34(three_pin)}

        prompted_game, events = process_discard_phase(game_state, three_pin)
        prompt = prompted_game.round_state.pending_call_prompt
        assert prompt is not None
        chi = MeldOption(call_type=MeldCallType.CHI, options=((one_pin, two_pin),))
        assert prompt.callers == (Caller(seat=1, can_ron=True, melds=(chi,)), Caller(seat=2, can_ron=True))
        assert [(e.target, e.call_type) for e in events if isinstance(e, CallPromptEvent)] == [
            (SeatTarget(seat=1), CallType.RON),
            (SeatTarget(seat=2), CallType.RON),
        ]

        chi_result = handle_chi(
            prompted_game, seat=1, data=ChiActionData(tile_id=three_pin, sequence_tiles=(one_pin, two_pin))
        )
        assert chi_result.events == []

        ron_result = handle_ron(chi_result.state, seat=2)
        round_ends = [e for e in ron_result.events if isinstance(e, RoundEndEvent)]
        assert [(e.result.type, e.result.winner_seat) for e in round_ends] == [(RoundResultType.RON, 2)]
        assert not [e for e in ron_result.events if isinstance(e, MeldEvent)]


class TestRonPassMeldClaims:
    def test_discard_claim__when_ron_caller_passes_and_pon_claimed__should_execute_pon(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", sou="11")

        wall, dead_wall = _make_wall_and_dead_wall()
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=ron_hand),
            create_player(seat=2, tiles=(*pon_tiles, *other_tiles)),
            create_player(seat=3),
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        new_game, _events = process_discard_phase(game_state, discard_tile)
        new_round = new_game.round_state
        # simulate: B passes (ron caller), C calls pon
        prompt = new_round.pending_call_prompt
        assert prompt is not None

        resolved_prompt = prompt.model_copy(
            update={
                "pending_seats": frozenset(),
                "responses": (CallResponse(seat=2, action=GameAction.CALL_PON),),
            },
        )
        new_round = new_round.model_copy(update={"pending_call_prompt": resolved_prompt})
        new_game = update_game_with_round(new_game, new_round)

        result = resolve_call_prompt(new_game)
        # pon should execute - no DrawEvent, only MeldEvent
        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 0
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 2
        # round should NOT be finished
        assert result.state.round_state.phase == RoundPhase.PLAYING


class TestAllCallersPass:
    def test_discard_claim__when_all_callers_pass__should_advance_turn(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", sou="11")

        wall, dead_wall = _make_wall_and_dead_wall()
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=ron_hand),
            create_player(seat=2, tiles=(*pon_tiles, *other_tiles)),
            create_player(seat=3),
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        new_game, _events = process_discard_phase(game_state, discard_tile)
        new_round = new_game.round_state
        # all pass
        prompt = new_round.pending_call_prompt
        assert prompt is not None

        resolved_prompt = prompt.model_copy(
            update={"pending_seats": frozenset(), "responses": ()},
        )
        new_round = new_round.model_copy(update={"pending_call_prompt": resolved_prompt})
        new_game = update_game_with_round(new_game, new_round)

        result = resolve_call_prompt(new_game)
        # turn should advance, prompt cleared
        assert result.state.round_state.pending_call_prompt is None
        assert result.state.round_state.current_player_seat != 0


class TestMultipleRonPlusMeld:
    def test_discard_claim__when_two_ron_callers_and_meld_caller__should_resolve_double_ron(self):
        ron_hand_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        ron_hand_2 = tuple(TilesConverter.string_to_136_array(sou="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        wall, dead_wall = _make_wall_and_dead_wall()
        players = (
            create_player(seat=0),
            create_player(seat=1, tiles=ron_hand_1),
            create_player(seat=2, tiles=ron_hand_2),
            create_player(seat=3),
        )

        # set up prompt directly: seats 1 and 2 are ron callers, seat 3 is meld
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                Caller(seat=1, can_ron=True),
                Caller(seat=2, can_ron=True),
                Caller(seat=3, melds=(MeldOption(call_type=MeldCallType.PON),)),
            ),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
            ),
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(game_state)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestAllRonPassMeldWins:
    def test_discard_claim__when_ron_callers_pass_and_pon_and_chi_claimed__should_execute_pon(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        chi_tiles = TilesConverter.string_to_136_array(pin="24")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", sou="11")
        wall, dead_wall = _make_wall_and_dead_wall()

        # seat 2 has pon tiles, seat 3 has chi tiles, seat 1 is ron caller (will pass)
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                Caller(seat=1, can_ron=True),
                Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.PON),)),
                Caller(
                    seat=3, melds=(MeldOption(call_type=MeldCallType.CHI, options=((chi_tiles[0], chi_tiles[1]),)),)
                ),
            ),
            responses=(
                CallResponse(seat=2, action=GameAction.CALL_PON),
                CallResponse(seat=3, action=GameAction.CALL_CHI, sequence_tiles=(chi_tiles[0], chi_tiles[1])),
            ),
        )

        players = (
            create_player(seat=0),
            create_player(seat=1),
            create_player(seat=2, tiles=(*pon_tiles, *other_tiles)),
            create_player(seat=3, tiles=(*chi_tiles, *other_tiles)),
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(game_state)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 2  # pon wins over chi


class TestDualEligibleSeatRonAndMeld:
    def test_discard_claim__when_seat_can_ron_and_pon_and_chooses_pon__should_offer_both_and_make_it_furiten(self):
        three_pin = tile_copies(2, pin="3")[0]
        dealer_hand = (*tile_copies(0, honors="1234567"), *tile_copies(1, honors="123456"), three_pin)
        ittsu_shanpon_on_three_and_five_pin = (*tile_copies(0, man="123456789", pin="35"), *tile_copies(1, pin="35"))
        no_pin_hand = (*tile_copies(0, sou="123456789"), *tile_copies(2, honors="1234"))
        other_no_pin_hand = (*tile_copies(1, sou="123456789"), *tile_copies(2, sou="1234"))
        players = (
            create_player(seat=0, tiles=dealer_hand),
            create_player(seat=1, tiles=ittsu_shanpon_on_three_and_five_pin),
            create_player(seat=2, tiles=no_pin_hand),
            create_player(seat=3, tiles=other_no_pin_hand),
        )
        round_state = create_round_state(
            players=players,
            wall=tile_copies(2, man="123456789"),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)
        assert get_waiting_tiles(players[1]) == {tile_to_34(three_pin), tile_to_34(tile_copies(0, pin="5")[0])}

        prompted_game, events = process_discard_phase(game_state, three_pin)
        prompt = prompted_game.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (Caller(seat=1, can_ron=True, melds=(MeldOption(call_type=MeldCallType.PON),)),)
        assert [(e.target, e.call_type, e.callers) for e in events if isinstance(e, CallPromptEvent)] == [
            (SeatTarget(seat=1), CallType.RON, [MeldCaller(seat=1, call_type=MeldCallType.PON)]),
        ]

        result = handle_pon(prompted_game, seat=1, data=PonActionData(tile_id=three_pin))
        melds = [e for e in result.events if isinstance(e, MeldEvent)]
        assert [(e.caller_seat, e.called_tile_id) for e in melds] == [(1, three_pin)]
        assert [e.target for e in result.events if isinstance(e, TurnEvent)] == [SeatTarget(seat=1)]
        assert result.state.round_state.pending_call_prompt is None
        assert result.state.round_state.players[1].is_temporary_furiten is True

    def test_discard_claim__when_seat_chooses_chi_over_ron_and_loses_it_to_a_pon__should_be_furiten_on_its_other_wait(
        self,
    ):
        four_pin = tile_copies(3, pin="4")[0]
        two_pin, three_pin = tile_copies(0, pin="23")
        other_winning_one_pin = tile_copies(1, pin="1")[0]
        dealer_hand = (*tile_copies(1, honors="1234567"), *tile_copies(2, honors="123456"), four_pin)
        man_ittsu_on_one_and_four_pin = (*tile_copies(0, man="123456789", pin="235"), *tile_copies(1, pin="5"))
        pon_hand_holding_one_pin = (
            *tile_copies(1, pin="4"),
            *tile_copies(2, pin="4"),
            other_winning_one_pin,
            *tile_copies(0, sou="13579", honors="12345"),
        )
        no_pin_hand = (*tile_copies(1, man="123456789"), *tile_copies(0, sou="2468"))
        players = (
            create_player(seat=0, tiles=dealer_hand),
            create_player(seat=1, tiles=man_ittsu_on_one_and_four_pin),
            create_player(seat=2, tiles=pon_hand_holding_one_pin),
            create_player(seat=3, tiles=no_pin_hand),
        )
        round_state = create_round_state(
            players=players,
            wall=tile_copies(2, man="123456789"),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)
        assert get_waiting_tiles(players[1]) == {tile_to_34(other_winning_one_pin), tile_to_34(four_pin)}

        prompted_game, _events = process_discard_phase(game_state, four_pin)
        prompt = prompted_game.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, c.can_ron, [m.call_type for m in c.melds]) for c in prompt.callers] == [
            (1, True, [MeldCallType.CHI]),
            (2, False, [MeldCallType.PON]),
        ]

        chi_result = handle_chi(
            prompted_game, seat=1, data=ChiActionData(tile_id=four_pin, sequence_tiles=(two_pin, three_pin))
        )
        pon_result = handle_pon(chi_result.state, seat=2, data=PonActionData(tile_id=four_pin))
        assert [e.caller_seat for e in pon_result.events if isinstance(e, MeldEvent)] == [2]
        assert pon_result.state.round_state.players[1].is_temporary_furiten is True

        discard_result = handle_discard(pon_result.state, seat=2, data=DiscardActionData(tile_id=other_winning_one_pin))
        assert not [e for e in discard_result.events if isinstance(e, CallPromptEvent)]
        assert discard_result.state.round_state.pending_call_prompt is None


class TestDualEligibleSeatPassFuriten:
    def test_discard_claim__when_pass_on_ron_eligible_discard__should_apply_furiten(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, can_ron=True),),
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = handle_pass(game_state, seat=1)
        assert result.state.round_state.players[1].is_temporary_furiten is True

    def test_discard_claim__when_pass_on_meld_only_discard__should_not_apply_furiten(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({2}),
            callers=(Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = handle_pass(game_state, seat=2)
        assert result.state.round_state.players[2].is_temporary_furiten is False


class TestRiichiFinalizationAfterRonPass:
    def test_discard_claim__when_riichi_discard_claimed_by_meld__should_finalize_riichi_first(self):
        discard_tile = TilesConverter.string_to_136_array(sou="5")[0]
        pon_tiles = TilesConverter.string_to_136_array(sou="55")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", pin="11")

        wall, dead_wall = _make_wall_and_dead_wall()
        players = (
            create_player(
                seat=0,
                tiles=tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113")),
                # seat 0 is the discarder, about to finalize riichi
                discards=(Discard(tile_id=discard_tile, is_riichi_discard=True),),
            ),
            create_player(seat=1),
            create_player(seat=2, tiles=(*pon_tiles, *other_tiles)),
            create_player(seat=3),
        )

        # create a DISCARD prompt with seat 1 as ron caller (already passed) and seat 2 as meld
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.PON),))),
            responses=(CallResponse(seat=2, action=GameAction.CALL_PON),),
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(game_state)
        # riichi should be finalized first
        riichi_events = [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert len(riichi_events) == 1
        assert riichi_events[0].seat == 0
        # meld (pon) should execute - no DrawEvent, only MeldEvent
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 2


class TestHandleRonOnDiscardPrompt:
    def test_discard_claim__when_ron_called_with_other_callers_pending__should_record_response_and_keep_prompt(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.PON),))),
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = (
            create_player(seat=0),
            create_player(seat=1, tiles=ron_hand),
            create_player(seat=2),
            create_player(seat=3),
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = handle_ron(game_state, seat=1)
        # should record response and wait for seat 2
        assert result.state.round_state.pending_call_prompt is not None
        responses = result.state.round_state.pending_call_prompt.responses
        assert len(responses) == 1
        assert responses[0].seat == 1
        assert responses[0].action == GameAction.CALL_RON


class TestHandlePassThenResolve:
    def test_discard_claim__when_both_callers_pass__should_clear_prompt_and_advance_turn(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.PON),))),
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        # seat 1 passes (ron caller -> furiten applied)
        result1 = handle_pass(game_state, seat=1)
        assert result1.state.round_state.players[1].is_temporary_furiten is True

        # seat 2 passes (meld caller -> no furiten)
        result2 = handle_pass(result1.state, seat=2)
        # should be resolved (turn advanced)
        assert result2.state.round_state.pending_call_prompt is None
        assert result2.state.round_state.current_player_seat != 0


class TestLastDiscardRestriction:
    def test_discard_claim__when_last_discard__should_block_pon(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        # tiles that do NOT form a winning hand with pin333
        other_tiles = TilesConverter.string_to_136_array(man="1234", sou="1234567")

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="88889999", pin="112266"))
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1),
            create_player(seat=2, tiles=(*pon_tiles, *other_tiles)),
            create_player(seat=3),
        )

        # empty live wall: last tile was already drawn
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_discard_phase(game_state, discard_tile)
        # no call prompt should be created (no ron callers either in this scenario)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert len(call_prompts) == 0

    def test_discard_claim__when_last_discard__should_block_chi(self):
        discard_tile = TilesConverter.string_to_136_array(pin="5")[0]
        chi_tiles = TilesConverter.string_to_136_array(pin="46")
        # tiles that do NOT form a winning hand with pin456
        other_tiles = TilesConverter.string_to_136_array(man="1234", sou="1234567")

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="88889999", pin="112233"))
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=(*chi_tiles, *other_tiles)),
            create_player(seat=2),
            create_player(seat=3),
        )

        # empty live wall
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_discard_phase(game_state, discard_tile)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert len(call_prompts) == 0

    def test_discard_claim__when_last_discard__should_allow_ron(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333366"))
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=ron_hand),
            create_player(seat=2),
            create_player(seat=3),
        )

        # empty live wall
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_discard_phase(game_state, discard_tile)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert [(e.call_type, e.target) for e in call_prompts] == [(CallType.RON, SeatTarget(seat=1))]

    def test_discard_claim__when_last_discard_pon_and_ron_possible__should_offer_ron_only(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        # tiles that do NOT form a winning hand with pin333
        other_tiles = TilesConverter.string_to_136_array(man="1234", sou="1234567")

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="88889999", pin="112266"))
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=ron_hand),
            create_player(seat=2, tiles=(*pon_tiles, *other_tiles)),
            create_player(seat=3),
        )

        # empty live wall
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_discard_phase(game_state, discard_tile)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert [(e.call_type, e.target) for e in call_prompts] == [(CallType.RON, SeatTarget(seat=1))]
