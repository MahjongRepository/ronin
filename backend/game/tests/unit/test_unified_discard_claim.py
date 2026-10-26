from game.logic.action_handlers import handle_chi, handle_discard, handle_pass, handle_pon, handle_riichi, handle_ron
from game.logic.action_result import ActionResult
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import (
    CallType,
    GameAction,
    MeldCallType,
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
from game.logic.melds import can_call_chi, can_call_pon
from game.logic.runtime import GameRuntime
from game.logic.state import (
    Caller,
    CallResponse,
    MahjongGameState,
    MeldOption,
)
from game.logic.tiles import tile_to_34
from game.logic.turn import process_discard_phase
from game.logic.types import ChiActionData, DiscardActionData, MeldCaller, PonActionData, RiichiActionData
from game.logic.win import get_waiting_tiles
from game.tests.conftest import create_dealt_game_state, create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _update_round_state


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


_DISCARDED_THREE_PIN = tile_copies(3, pin="3")[0]


def _dealer_about_to_discard_three_pin() -> MahjongGameState:
    ittsu_on_three_or_four_pin = (*tile_copies(0, man="123456789", pin="3"), *tile_copies(0, pin="555"))
    players = (
        create_player(seat=0, tiles=(*tile_copies(0, sou="123456789", honors="1122"), _DISCARDED_THREE_PIN)),
        create_player(seat=1, tiles=ittsu_on_three_or_four_pin),
        create_player(seat=2, tiles=(*tile_copies(1, pin="33"), *tile_copies(1, man="1357", sou="13579", honors="34"))),
        create_player(seat=3, tiles=(*tile_copies(2, sou="123456789"), *tile_copies(2, honors="1234"))),
    )
    game_state = create_dealt_game_state(players)
    assert tile_to_34(_DISCARDED_THREE_PIN) in get_waiting_tiles(players[1])
    return game_state


def _discard_three_pin(game_state: MahjongGameState) -> ActionResult:
    result = handle_discard(game_state, seat=0, data=DiscardActionData(tile_id=_DISCARDED_THREE_PIN))
    assert isinstance(result, ActionResult)
    prompt = result.state.round_state.pending_call_prompt
    assert prompt is not None
    assert prompt.callers == (
        Caller(seat=1, can_ron=True),
        Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.PON),)),
    )
    return result


class TestRonPassMeldClaims:
    def test_discard_claim__when_ron_caller_passes_and_pon_claimed__should_execute_pon(self):
        prompted = _discard_three_pin(_dealer_about_to_discard_three_pin())

        passed = handle_pass(prompted.state, seat=1)
        result = handle_pon(passed.state, seat=2, data=PonActionData(tile_id=_DISCARDED_THREE_PIN))
        assert [(e.caller_seat, e.called_tile_id) for e in result.events if isinstance(e, MeldEvent)] == [
            (2, _DISCARDED_THREE_PIN)
        ]
        assert not [e for e in result.events if isinstance(e, DrawEvent)]
        assert result.state.round_state.phase == RoundPhase.PLAYING


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


class TestRiichiFinalizationAfterRonPass:
    def test_discard_claim__when_riichi_discard_claimed_by_meld__should_finalize_riichi_first(self):
        game_state = _dealer_about_to_discard_three_pin()

        riichi = handle_riichi(game_state, seat=0, data=RiichiActionData(tile_id=_DISCARDED_THREE_PIN))
        passed = handle_pass(riichi.state, seat=1)
        pon = handle_pon(passed.state, seat=2, data=PonActionData(tile_id=_DISCARDED_THREE_PIN))
        assert [type(e) for e in pon.events if isinstance(e, (RiichiDeclaredEvent, MeldEvent))] == [
            RiichiDeclaredEvent,
            MeldEvent,
        ]
        assert pon.state.round_state.players[0].is_riichi is True
        assert [e.caller_seat for e in pon.events if isinstance(e, MeldEvent)] == [2]


class TestHandleRonOnDiscardPrompt:
    def test_discard_claim__when_ron_called_with_other_callers_pending__should_record_response_and_keep_prompt(self):
        prompted = _discard_three_pin(_dealer_about_to_discard_three_pin())

        result = handle_ron(prompted.state, seat=1)
        assert result.events == []
        prompt = result.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.responses == (CallResponse(seat=1, action=GameAction.CALL_RON),)
        assert prompt.pending_seats == frozenset({2})


class TestHandlePassThenResolve:
    def test_discard_claim__when_both_callers_pass__should_clear_prompt_and_advance_turn(self):
        prompted = _discard_three_pin(_dealer_about_to_discard_three_pin())

        ron_seat_passed = handle_pass(prompted.state, seat=1)
        assert ron_seat_passed.state.round_state.players[1].is_temporary_furiten is True

        meld_seat_passed = handle_pass(ron_seat_passed.state, seat=2)
        assert meld_seat_passed.state.round_state.players[2].is_temporary_furiten is False
        assert meld_seat_passed.state.round_state.pending_call_prompt is None
        assert meld_seat_passed.state.round_state.current_player_seat == 1


class TestLastDiscardRestriction:
    def test_discard_claim__when_last_discard_can_be_ronned_ponned_and_chied__should_offer_ron_only(self):
        last_three_pin = tile_copies(3, pin="3")[0]
        dealer_hand = (
            last_three_pin,
            tile_copies(0, pin="3")[0],
            *tile_copies(3, sou="123456789"),
            *tile_copies(0, honors="567"),
        )
        chi_hand = (
            *tile_copies(1, pin="4"),
            *tile_copies(3, pin="5"),
            *tile_copies(1, man="1357", sou="13579", honors="12"),
        )
        pon_hand = (*tile_copies(1, pin="33"), *tile_copies(2, man="1357", sou="13579", honors="34"))
        kanchan_on_three_pin = (*tile_copies(0, man="123456789", pin="24"), *tile_copies(1, pin="55"))
        players = (
            create_player(seat=0, tiles=dealer_hand),
            create_player(seat=1, tiles=chi_hand),
            create_player(seat=2, tiles=pon_hand),
            create_player(seat=3, tiles=kanchan_on_three_pin),
        )
        runtime = GameRuntime(game_id="game", state=create_dealt_game_state(players), ai=AIPlayerController({}))
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))
        settings = runtime.state.settings
        assert can_call_chi(
            players[1], discarded_tile=last_three_pin, discarder_seat=0, caller_seat=1, settings=settings
        )
        assert can_call_pon(players[2], last_three_pin)
        assert get_waiting_tiles(players[3]) == {tile_to_34(last_three_pin)}

        _new_game, events = process_discard_phase(runtime.state, last_three_pin)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert [(e.call_type, e.target) for e in call_prompts] == [(CallType.RON, SeatTarget(seat=3))]
