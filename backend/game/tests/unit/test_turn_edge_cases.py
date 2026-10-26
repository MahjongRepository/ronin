from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import AbortiveDrawType
from game.logic.action_handlers import handle_discard, handle_kan, handle_pass, handle_riichi, handle_ron, handle_tsumo
from game.logic.action_result import ActionResult
from game.logic.actions import get_available_actions
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import (
    CallType,
    GameAction,
    KanType,
    MeldCallType,
    PlayerAction,
    PromptKind,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    FuritenEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    SeatTarget,
)
from game.logic.exceptions import ScoringError
from game.logic.furiten_tracker import FuritenTracker
from game.logic.meld_wrapper import FrozenMeld
from game.logic.runtime import GameRuntime
from game.logic.scoring import HandResult, ScoringContext, calculate_hand_value_with_tiles
from game.logic.state import Caller, Discard, MahjongGameState, MeldOption
from game.logic.tiles import tile_to_34
from game.logic.turn import (
    _maybe_emit_dora_event,
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
)
from game.logic.types import DiscardActionData, KanActionData, MeldCallInput, RiichiActionData
from game.logic.win import get_waiting_tiles
from game.tests.conftest import create_dealt_game_state, create_player, create_round_state
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
    tile_copies,
)
from game.tests.unit.helpers import _update_round_state

if TYPE_CHECKING:
    from collections.abc import Sequence


def _create_pin_3_discard_with_three_ron_callers() -> MahjongGameState:
    players = (
        create_player(seat=0, tiles=(*PIN_3_TRIPLE_RON_DEALER_HAND, PIN_3_TRIPLE_RON_DISCARD)),
        *(create_player(seat=seat, tiles=hand) for seat, hand in enumerate(PIN_3_TRIPLE_RON_CALLER_HANDS, start=1)),
    )
    return create_dealt_game_state(players, riichi_sticks=1)


def _respond_to_call_prompt(game_state: MahjongGameState, responses: dict[int, GameAction]) -> ActionResult:
    result = ActionResult([], state=game_state)
    for seat, action in responses.items():
        handler = handle_ron if action == GameAction.CALL_RON else handle_pass
        result = handler(result.state, seat=seat)
        assert isinstance(result, ActionResult)

    return result


_JUNK_HANDS = {copy: tuple(tile_copies(copy, man="1357", pin="2468", sou="13579")) for copy in (1, 2, 3)}


class TestKyuushuKyuuhaiDrawPhase:
    def test_kyuushu_kyuuhai__when_in_draw_phase__should_be_available(self):
        nine_terminal_types = tile_copies(0, man="192244", pin="19", sou="19", honors="123")
        players = (
            create_player(seat=0, tiles=nine_terminal_types),
            *(create_player(seat=seat, tiles=_JUNK_HANDS[seat]) for seat in (1, 2, 3)),
        )
        game_state = create_dealt_game_state(players, draws=tile_copies(0, man="6"))

        _new_game, events = process_draw_phase(game_state)
        draw_events = [e for e in events if isinstance(e, DrawEvent) and e.available_actions]
        assert len(draw_events) == 1
        available_actions = [a.action for a in draw_events[0].available_actions]
        assert PlayerAction.KYUUSHU in available_actions


class TestRinshanTsumoAfterOpenKan:
    def test_tsumo__when_open_kan_replacement_completes_hand__should_be_offered_and_accepted(self):
        one_man = tile_copies(0, man="1111")
        five_sou_tanki, rinshan_five_sou = tile_copies(0, sou="55")
        players = (
            create_player(
                seat=0, tiles=(one_man[3], *tile_copies(0, honors="1234567"), *tile_copies(1, honors="123456"))
            ),
            create_player(seat=1, tiles=(*one_man[:3], *tile_copies(0, pin="234567", sou="789"), five_sou_tanki)),
            create_player(seat=2, tiles=tile_copies(2, man="456789", honors="1234567")),
            create_player(seat=3, tiles=tile_copies(3, man="456789", honors="1234567")),
        )
        game_state = create_dealt_game_state(players, rinshan_draws=(rinshan_five_sou,))
        prompted, _events = process_discard_phase(game_state, one_man[3])
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, [m.call_type for m in c.melds]) for c in prompt.callers] == [
            (1, [MeldCallType.OPEN_KAN, MeldCallType.PON]),
        ]

        kan = handle_kan(prompted, seat=1, data=KanActionData(tile_id=one_man[3], kan_type=KanType.OPEN))
        assert isinstance(kan, ActionResult)
        assert kan.state.round_state.players[1].tiles[-1] == rinshan_five_sou
        assert PlayerAction.TSUMO in [a.action for a in get_available_actions(kan.state, seat=1)]

        tsumo = handle_tsumo(kan.state, seat=1)
        round_ends = [e.result for e in tsumo.events if isinstance(e, RoundEndEvent)]
        assert [(r.type, r.winner_seat) for r in round_ends] == [(RoundResultType.TSUMO, 1)]


class TestExhaustiveDrawPhase:
    def test_process_draw_phase__when_live_wall_empty__should_end_round_with_exhaustive_draw(self):
        last_discard = tile_copies(0, honors="7")[0]
        players = (
            create_player(seat=0, tiles=(last_discard, *tile_copies(0, man="123456789", pin="1255"))),
            *(create_player(seat=seat, tiles=_JUNK_HANDS[seat]) for seat in (1, 2, 3)),
        )
        runtime = GameRuntime(game_id="game", state=create_dealt_game_state(players), ai=AIPlayerController({}))
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))
        discarded = handle_discard(runtime.state, seat=0, data=DiscardActionData(tile_id=last_discard))
        assert isinstance(discarded, ActionResult)
        assert discarded.state.round_state.pending_call_prompt is None
        assert discarded.state.round_state.current_player_seat == 1

        new_game, events = process_draw_phase(discarded.state)
        assert new_game.round_state.phase == RoundPhase.FINISHED
        assert [type(e) for e in events] == [RoundEndEvent]
        assert events[0].result.type == RoundResultType.EXHAUSTIVE_DRAW
        assert events[0].result.tempai_seats == [0]


_RIICHI_FURITEN_DISCARDED_THREE_PIN = tile_copies(2, pin="3")[0]
_RIICHI_FURITEN_LATER_THREE_PIN = tile_copies(3, pin="3")[0]
_RIICHI_SEAT_DRAW = tile_copies(1, honors="7")[0]
_RIICHI_FURITEN_SEAT_2_DRAW = tile_copies(2, honors="7")[0]


def _riichi_seat_waiting_on_three_pin(*, earlier_discards: tuple[Discard, ...] = ()) -> MahjongGameState:
    riichi_discard = Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True)
    players = (
        create_player(
            seat=0,
            tiles=(
                _RIICHI_FURITEN_DISCARDED_THREE_PIN,
                *tile_copies(0, sou="123456789"),
                *tile_copies(1, honors="1234"),
            ),
        ),
        create_player(
            seat=1,
            tiles=tile_copies(0, man="123456789", pin="1255"),
            discards=(*earlier_discards, riichi_discard),
            is_riichi=True,
        ),
        create_player(
            seat=2,
            tiles=(_RIICHI_FURITEN_LATER_THREE_PIN, *tile_copies(1, sou="123456789"), *tile_copies(2, honors="123")),
        ),
        create_player(seat=3, tiles=(*tile_copies(2, sou="123456789"), *tile_copies(3, honors="1234"))),
    )
    game_state = create_dealt_game_state(players, draws=(_RIICHI_SEAT_DRAW, _RIICHI_FURITEN_SEAT_2_DRAW))
    assert get_waiting_tiles(players[1]) == {tile_to_34(_RIICHI_FURITEN_DISCARDED_THREE_PIN)}
    return game_state


class TestRiichiFuriten:
    def test_riichi_furiten__when_riichi_player_discarded_winning_tile__should_flag_riichi_furiten(self):
        game_state = _riichi_seat_waiting_on_three_pin(earlier_discards=(Discard(tile_id=tile_copies(1, pin="3")[0]),))

        new_game, _events = process_discard_phase(game_state, _RIICHI_FURITEN_DISCARDED_THREE_PIN)
        assert new_game.round_state.pending_call_prompt is None
        assert new_game.round_state.players[1].is_riichi_furiten is True

    def test_riichi_furiten__when_riichi_player_passes_winning_tile__should_block_ron_for_rest_of_hand(self):
        game_state = _riichi_seat_waiting_on_three_pin()

        prompted, _events = process_discard_phase(game_state, _RIICHI_FURITEN_DISCARDED_THREE_PIN)
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (Caller(seat=1, can_ron=True),)
        assert prompted.round_state.players[1].is_riichi_furiten is False

        passed = handle_pass(prompted, seat=1)
        assert isinstance(passed, ActionResult)
        assert passed.state.round_state.players[1].tiles[-1] == _RIICHI_SEAT_DRAW
        assert passed.state.round_state.players[1].is_riichi_furiten is True

        own_discard = handle_discard(passed.state, seat=1, data=DiscardActionData(tile_id=_RIICHI_SEAT_DRAW))
        assert isinstance(own_discard, ActionResult)
        assert own_discard.state.round_state.players[1].is_riichi_furiten is True

        later_wait = _discard_after_draw(own_discard.state, seat=2, tile_id=_RIICHI_FURITEN_LATER_THREE_PIN)
        assert later_wait.state.round_state.pending_call_prompt is None
        assert later_wait.state.round_state.players[1].is_riichi_furiten is True


def _discard_after_draw(game_state: MahjongGameState, seat: int, tile_id: int) -> ActionResult:
    drawn_game, _events = process_draw_phase(game_state)
    assert drawn_game.round_state.current_player_seat == seat
    result = handle_discard(drawn_game, seat=seat, data=DiscardActionData(tile_id=tile_id))
    assert isinstance(result, ActionResult)
    return result


class TestTemporaryFuriten:
    def test_temporary_furiten__when_winning_tile_without_yaku_passes__should_block_ron_until_own_discard(self):
        three_man_without_yaku = tile_copies(1, man="3")[0]
        six_man_with_ittsu = tile_copies(1, man="6")[0]
        later_six_man_with_ittsu = tile_copies(2, man="6")[0]
        seat_3_draw = tile_copies(1, honors="5")[0]
        seat_0_draw = tile_copies(1, honors="7")[0]
        seat_1_draw = tile_copies(0, honors="6")[0]
        ittsu_on_six_man = (
            *tile_copies(0, man="12345789", pin="9", sou="22"),
            *tile_copies(1, pin="9"),
            *tile_copies(2, pin="9"),
        )
        players = (
            create_player(seat=0, tiles=(*tile_copies(1, pin="12345678", sou="9"), *tile_copies(2, honors="1234"))),
            create_player(seat=1, tiles=ittsu_on_six_man, discards=(Discard(tile_id=tile_copies(0, honors="7")[0]),)),
            create_player(seat=2, tiles=(*tile_copies(0, sou="13456789", honors="12345"), three_man_without_yaku)),
            create_player(
                seat=3, tiles=(six_man_with_ittsu, *tile_copies(0, pin="12345678"), *tile_copies(1, honors="1234"))
            ),
        )
        game_state = create_dealt_game_state(
            players,
            draws=(seat_3_draw, seat_0_draw, seat_1_draw, later_six_man_with_ittsu),
            current_player_seat=2,
        )
        assert get_waiting_tiles(players[1]) == {tile_to_34(three_man_without_yaku), tile_to_34(six_man_with_ittsu)}
        furiten = FuritenTracker()

        passed = handle_discard(game_state, seat=2, data=DiscardActionData(tile_id=three_man_without_yaku))
        assert isinstance(passed, ActionResult)
        assert passed.state.round_state.pending_call_prompt is None
        assert [e.data for e in furiten.check_changes(passed.state.round_state)] == [
            FuritenEvent(is_furiten=True, target=SeatTarget(seat=1)),
        ]

        missed = _discard_after_draw(passed.state, seat=3, tile_id=six_man_with_ittsu)
        assert not [e for e in missed.events if isinstance(e, CallPromptEvent)]
        assert missed.state.round_state.pending_call_prompt is None

        before_own_discard = _discard_after_draw(missed.state, seat=0, tile_id=seat_0_draw)
        own_discard = _discard_after_draw(before_own_discard.state, seat=1, tile_id=seat_1_draw)
        assert own_discard.state.round_state.players[1].is_temporary_furiten is False
        assert [e.data for e in furiten.check_changes(own_discard.state.round_state)] == [
            FuritenEvent(is_furiten=False, target=SeatTarget(seat=1)),
        ]

        offered = _discard_after_draw(own_discard.state, seat=2, tile_id=later_six_man_with_ittsu)
        prompt = offered.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (Caller(seat=1, can_ron=True),)


class TestFindRonCallers:
    def test_find_ron_callers__when_multiple_callers__should_sort_by_distance_from_discarder(self):
        three_pin = tile_copies(3, pin="3")[0]
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="123456789", pin="1255")),
            create_player(seat=1, tiles=tile_copies(2, sou="123456789", honors="1234")),
            create_player(seat=2, tiles=(*tile_copies(3, sou="123456789", honors="1234"), three_pin)),
            create_player(seat=3, tiles=(*tile_copies(1, man="123456789", pin="12"), *tile_copies(2, pin="55"))),
        )
        game_state = create_dealt_game_state(players, current_player_seat=2)
        assert get_waiting_tiles(players[0]) == get_waiting_tiles(players[3]) == {tile_to_34(three_pin)}

        prompted_game, _events = process_discard_phase(game_state, three_pin)
        prompt = prompted_game.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, c.can_ron) for c in prompt.callers] == [(3, True), (0, True)]


class TestSingleRonHandError:
    def test_single_ron__when_hand_result_error__should_raise(self):
        prompted, _events = process_discard_phase(
            _create_pin_3_discard_with_three_ron_callers(), PIN_3_TRIPLE_RON_DISCARD
        )
        others_passed = _respond_to_call_prompt(prompted, {2: GameAction.PASS, 3: GameAction.PASS})

        with (
            patch("game.logic.turn.calculate_hand_value_with_tiles", return_value=HandResult(error="mock error")),
            pytest.raises(ScoringError, match="ron calculation error"),
        ):
            handle_ron(others_passed.state, seat=1)


class TestDoubleRonHandError:
    def test_double_ron__when_second_winner_scoring_fails__should_raise_scoring_error_blaming_nobody(self):
        prompted, _events = process_discard_phase(
            _create_pin_3_discard_with_three_ron_callers(), PIN_3_TRIPLE_RON_DISCARD
        )
        first_winner_declared = _respond_to_call_prompt(prompted, {1: GameAction.CALL_RON, 3: GameAction.PASS})

        def fail_for_second_winner(ctx: ScoringContext, *, tiles: list[int], win_tile: int) -> HandResult:
            if ctx.player.seat == 2:
                return HandResult(error="mock error")

            return calculate_hand_value_with_tiles(ctx, tiles=tiles, win_tile=win_tile)

        with (
            patch("game.logic.turn.calculate_hand_value_with_tiles", side_effect=fail_for_second_winner),
            pytest.raises(ScoringError, match="ron calculation error for seat 2"),
        ):
            handle_ron(first_winner_declared.state, seat=2)


class TestTsumoHandError:
    def test_tsumo__when_scoring_library_fails__should_raise_scoring_error_not_kick(self):
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="123456789", pin="12355")),
            *(create_player(seat=seat, tiles=_JUNK_HANDS[seat]) for seat in (1, 2, 3)),
        )
        game_state = create_dealt_game_state(players)

        with (
            patch("game.logic.turn.calculate_hand_value", return_value=HandResult(error="mock error")),
            pytest.raises(ScoringError, match="tsumo calculation error"),
        ):
            handle_tsumo(game_state, seat=0)


_ONE_MAN = tuple(tile_copies(copy, man="1")[0] for copy in range(4))


def _declare_one_man_added_kan(*, seat_1_hand: Sequence[int]) -> ActionResult:
    one_man_pon = FrozenMeld(
        meld_type=FrozenMeld.PON,
        tiles=_ONE_MAN[:3],
        opened=True,
        called_tile=_ONE_MAN[0],
        who=0,
        from_who=3,
    )
    players = (
        create_player(
            seat=0,
            tiles=(_ONE_MAN[3], *tile_copies(1, pin="123456789"), *tile_copies(0, honors="7")),
            melds=(one_man_pon,),
        ),
        create_player(seat=1, tiles=seat_1_hand),
        create_player(seat=2, tiles=tile_copies(2, sou="123456789", honors="1234")),
        create_player(
            seat=3,
            tiles=tile_copies(3, sou="123456789", honors="1234"),
            discards=(Discard(tile_id=_ONE_MAN[0]),),
        ),
    )
    game_state = create_dealt_game_state(players)

    result = handle_kan(game_state, seat=0, data=KanActionData(tile_id=_ONE_MAN[3], kan_type=KanType.ADDED))
    assert isinstance(result, ActionResult)
    return result


class TestAddedKanChankan:
    def test_added_kan__when_player_can_chankan__should_prompt_chankan(self):
        waiting_on_one_man = tile_copies(0, man="23456789", pin="456", sou="55")
        assert tile_to_34(_ONE_MAN[3]) in get_waiting_tiles(create_player(seat=1, tiles=waiting_on_one_man))

        result = _declare_one_man_added_kan(seat_1_hand=waiting_on_one_man)
        prompt = result.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.kind == PromptKind.CHANKAN
        assert prompt.callers == (Caller(seat=1, can_ron=True),)
        assert [(e.target, e.call_type) for e in result.events if isinstance(e, CallPromptEvent)] == [
            (SeatTarget(seat=1), CallType.CHANKAN),
        ]
        assert not [e for e in result.events if isinstance(e, MeldEvent)]


class TestChiSequenceTilesValidation:
    def test_chi__when_sequence_tiles_none__should_raise(self):
        five_man = tile_copies(0, man="5")[0]
        players = (
            create_player(seat=0, tiles=(five_man, *tile_copies(0, pin="123456789", honors="1234"))),
            create_player(seat=1, tiles=tile_copies(0, man="34", sou="123456789", honors="56")),
            create_player(seat=2, tiles=tile_copies(1, pin="123456789", honors="1234")),
            create_player(seat=3, tiles=tile_copies(2, sou="123456789", honors="1234")),
        )
        prompted, _events = process_discard_phase(create_dealt_game_state(players), five_man)
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, [m.call_type for m in c.melds]) for c in prompt.callers] == [(1, [MeldCallType.CHI])]

        meld_input = MeldCallInput(caller_seat=1, call_type=MeldCallType.CHI, tile_id=five_man, sequence_tiles=None)
        with pytest.raises(AssertionError, match="chi call requires sequence_tiles"):
            process_meld_call(prompted, meld_input=meld_input)


_FIVE_SOU = tile_copies(0, sou="5")[0]
_EIGHT_SOU = tile_copies(1, sou="8")[0]


def _declare_fourth_riichi(riichi_discard: int) -> ActionResult:
    kanchan_on_five_sou = tile_copies(0, man="123456789", pin="11", sou="46")
    players = (
        create_player(
            seat=0,
            tiles=(*tile_copies(2, man="123456789"), *tile_copies(0, honors="3344"), riichi_discard),
            discards=(Discard(tile_id=tile_copies(1, honors="5")[0]),),
        ),
        create_player(
            seat=1,
            tiles=kanchan_on_five_sou,
            discards=(Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True),),
            is_riichi=True,
            score=24000,
        ),
        create_player(
            seat=2,
            tiles=tile_copies(0, pin="234567", sou="789", honors="1122"),
            discards=(Discard(tile_id=tile_copies(0, honors="6")[0], is_riichi_discard=True),),
            is_riichi=True,
            score=24000,
        ),
        create_player(
            seat=3,
            tiles=tile_copies(1, man="123456789", pin="99", sou="13"),
            discards=(Discard(tile_id=tile_copies(0, honors="5")[0], is_riichi_discard=True),),
            is_riichi=True,
            score=24000,
        ),
    )
    game_state = create_dealt_game_state(players, riichi_sticks=3)
    assert get_waiting_tiles(players[1]) == {tile_to_34(_FIVE_SOU)}

    result = handle_riichi(game_state, seat=0, data=RiichiActionData(tile_id=riichi_discard))
    assert isinstance(result, ActionResult)
    return result


def _fourth_riichi_discard_with_ron_caller() -> ActionResult:
    result = _declare_fourth_riichi(_FIVE_SOU)
    prompt = result.state.round_state.pending_call_prompt
    assert prompt is not None
    assert prompt.callers == (Caller(seat=1, can_ron=True),)
    return result


class TestAbortiveDrawIntegration:
    def test_four_winds__when_fourth_same_wind_discard_declares_riichi__should_abort_without_the_bet(self):
        east = tuple(tile_copies(copy, honors="1")[0] for copy in range(4))
        players = (
            *(
                create_player(
                    seat=seat,
                    tiles=tile_copies(seat, man="123456789", pin="1234"),
                    discards=(Discard(tile_id=east[seat]),),
                )
                for seat in range(3)
            ),
            create_player(seat=3, tiles=(*tile_copies(3, man="123456789", pin="1234"), east[3])),
        )
        game_state = create_dealt_game_state(players, current_player_seat=3)

        new_game, events = process_discard_phase(game_state, east[3], is_riichi=True)
        assert [e.is_riichi for e in events if isinstance(e, DiscardEvent)] == [True]
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_WINDS
        assert not [e for e in events if isinstance(e, RiichiDeclaredEvent)]
        assert new_game.riichi_sticks == game_state.riichi_sticks
        assert [p.score for p in new_game.round_state.players] == [p.score for p in game_state.round_state.players]
        assert not new_game.round_state.players[3].is_riichi

    def test_triple_ron__when_three_ron_callers_declare_on_a_riichi_discard__should_abort_without_the_bet(self):
        game_state = _create_pin_3_discard_with_three_ron_callers()

        prompted_game, events = process_discard_phase(game_state, PIN_3_TRIPLE_RON_DISCARD, is_riichi=True)
        assert [e.is_riichi for e in events if isinstance(e, DiscardEvent)] == [True]
        prompt = prompted_game.round_state.pending_call_prompt
        assert prompt is not None
        chi = MeldOption(call_type=MeldCallType.CHI, options=(tuple(tile_copies(0, pin="12")),))
        assert prompt.callers == (
            Caller(seat=1, can_ron=True, melds=(chi,)),
            Caller(seat=2, can_ron=True),
            Caller(seat=3, can_ron=True),
        )
        assert not [e for e in events if isinstance(e, RoundEndEvent)]

        result = _respond_to_call_prompt(
            prompted_game,
            {1: GameAction.CALL_RON, 2: GameAction.CALL_RON, 3: GameAction.CALL_RON},
        )
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.TRIPLE_RON
        assert round_end_events[0].result.score_changes == {0: 0, 1: 0, 2: 0, 3: 0}
        assert result.state.round_state.phase == RoundPhase.FINISHED
        assert result.state.riichi_sticks == 1
        assert not [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert [p.score for p in result.state.round_state.players] == [p.score for p in game_state.round_state.players]
        assert not result.state.round_state.players[0].is_riichi

    def test_triple_ron__when_one_of_three_ron_callers_passes__should_resolve_double_ron(self):
        game_state = _create_pin_3_discard_with_three_ron_callers()

        prompted_game, _events = process_discard_phase(game_state, PIN_3_TRIPLE_RON_DISCARD)
        result = _respond_to_call_prompt(
            prompted_game,
            {1: GameAction.CALL_RON, 2: GameAction.PASS, 3: GameAction.CALL_RON},
        )
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        double_ron = round_end_events[0].result
        assert double_ron.type == RoundResultType.DOUBLE_RON
        assert [winner.winner_seat for winner in double_ron.winners] == [1, 3]
        assert double_ron.loser_seat == 0

    def test_four_riichi_abort__when_fourth_riichi_discard_is_ronned__should_score_the_ron_without_its_stick(self):
        discard = _fourth_riichi_discard_with_ron_caller()

        ron = handle_ron(discard.state, seat=1)
        assert isinstance(ron, ActionResult)
        round_ends = [e for e in ron.events if isinstance(e, RoundEndEvent)]
        assert len(round_ends) == 1
        assert round_ends[0].result.type == RoundResultType.RON
        assert round_ends[0].result.winner_seat == 1
        assert round_ends[0].result.riichi_sticks_collected == 3
        assert ron.state.round_state.players[0].is_riichi is False

    def test_four_riichi_abort__when_ron_caller_passes_fourth_riichi_discard__should_abort(self):
        discard = _fourth_riichi_discard_with_ron_caller()

        passed = handle_pass(discard.state, seat=1)
        assert isinstance(passed, ActionResult)
        assert passed.state.round_state.players[0].is_riichi is True
        assert [e for e in passed.events if isinstance(e, RiichiDeclaredEvent)] == [RiichiDeclaredEvent(seat=0)]
        round_ends = [e for e in passed.events if isinstance(e, RoundEndEvent)]
        assert len(round_ends) == 1
        assert round_ends[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_ends[0].result.reason == AbortiveDrawType.FOUR_RIICHI

    def test_four_riichi_abort__when_nobody_can_call_fourth_riichi_discard__should_abort_at_once(self):
        unclaimed = _declare_fourth_riichi(_EIGHT_SOU)

        assert unclaimed.state.round_state.pending_call_prompt is None
        assert unclaimed.state.round_state.players[0].is_riichi is True
        assert [type(e) for e in unclaimed.events] == [DiscardEvent, RiichiDeclaredEvent, RoundEndEvent]
        round_end = unclaimed.events[-1]
        assert isinstance(round_end, RoundEndEvent)
        assert round_end.result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end.result.reason == AbortiveDrawType.FOUR_RIICHI


class TestAddedKanNormalPath:
    def test_added_kan__when_no_chankan__should_upgrade_pon_to_shouminkan(self):
        result = _declare_one_man_added_kan(seat_1_hand=tile_copies(0, man="2468", pin="13579", honors="5566"))
        assert result.state.round_state.pending_call_prompt is None
        assert [type(e) for e in result.events] == [MeldEvent, DrawEvent]
        assert [m.type for m in result.state.round_state.players[0].melds] == [FrozenMeld.SHOUMINKAN]


class TestMaybeEmitDoraEvent:
    def test_dora_event__when_no_new_dora__should_emit_nothing(self):
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
        )

        events = []
        _maybe_emit_dora_event(old_dora_count=1, new_round_state=round_state, events=events)
        assert events == []

    def test_dora_event__when_one_new_dora__should_emit_one_event(self):
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),
        )

        events = []
        _maybe_emit_dora_event(old_dora_count=1, new_round_state=round_state, events=events)
        assert len(events) == 1
        assert events[0].tile_id == dead_wall[3]

    def test_dora_event__when_multiple_new_dora__should_emit_event_for_each(self):
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3], dead_wall[4]),
        )

        events = []
        _maybe_emit_dora_event(old_dora_count=1, new_round_state=round_state, events=events)
        assert len(events) == 2
        assert events[0].tile_id == dead_wall[3]
        assert events[1].tile_id == dead_wall[4]
