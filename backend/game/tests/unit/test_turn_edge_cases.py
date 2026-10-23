from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import AbortiveDrawType
from game.logic.action_handlers import handle_ron, handle_tsumo
from game.logic.actions import get_available_actions
from game.logic.enums import CallType, GameAction, MeldCallType, PlayerAction, PromptKind, RoundPhase, RoundResultType
from game.logic.events import CallPromptEvent, DrawEvent, RoundEndEvent
from game.logic.exceptions import InvalidRiichiError, ScoringError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import HandResult, ScoringContext, calculate_hand_value_with_tiles
from game.logic.settings import GameSettings
from game.logic.state import Caller, CallResponse, Discard, PendingCallPrompt
from game.logic.turn import (
    _maybe_emit_dora_event,
    _validate_riichi_discard,
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.logic.types import MeldCallInput, RonCallInput
from game.tests.conftest import create_game_state, create_player, create_round_state


class TestKyuushuKyuuhaiDrawPhase:
    def test_kyuushu_kyuuhai__when_in_draw_phase__should_be_available(self):
        kyuushu_tiles = tuple(
            TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123")
            + TilesConverter.string_to_136_array(man="22334"),
        )
        players = (
            create_player(seat=0, tiles=kyuushu_tiles),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            all_discards=(),
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_draw_phase(game_state)
        draw_events = [e for e in events if isinstance(e, DrawEvent) and e.available_actions]
        assert len(draw_events) == 1
        available_actions = [a.action for a in draw_events[0].available_actions]
        assert PlayerAction.KYUUSHU in available_actions


class TestRinshanTsumoAfterOpenKan:
    def test_tsumo__when_open_kan_replacement_completes_hand__should_be_offered_and_accepted(self):
        man_1s = TilesConverter.string_to_136_array(man="1111")
        sou_5s = TilesConverter.string_to_136_array(sou="55")
        waiting_hand = (*man_1s[:3], *TilesConverter.string_to_136_array(pin="234567", sou="789"), sou_5s[0])
        players = (
            create_player(seat=0),
            create_player(seat=1, tiles=waiting_hand),
            create_player(seat=2),
            create_player(seat=3),
        )
        dead_wall = (sou_5s[1], *TilesConverter.string_to_136_array(sou="1111222233334"))
        round_state = create_round_state(
            players=players,
            wall=tuple(TilesConverter.string_to_136_array(pin="9999")),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        kan_game, _events = process_meld_call(
            game_state,
            meld_input=MeldCallInput(caller_seat=1, call_type=MeldCallType.OPEN_KAN, tile_id=man_1s[3]),
        )
        assert PlayerAction.TSUMO in [a.action for a in get_available_actions(kan_game, seat=1)]

        _game, tsumo_events = process_tsumo_call(kan_game, winner_seat=1)
        assert tsumo_events[0].result.type == RoundResultType.TSUMO


class TestExhaustiveDrawPhase:
    def test_process_draw_phase__when_live_wall_empty__should_end_round_with_exhaustive_draw(self):
        round_state = create_round_state(wall=(), phase=RoundPhase.PLAYING, current_player_seat=0)
        game_state = create_game_state(round_state)

        new_game, events = process_draw_phase(game_state)
        new_round = new_game.round_state
        assert new_round.phase == RoundPhase.FINISHED
        assert not any(isinstance(e, DrawEvent) for e in events)
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.EXHAUSTIVE_DRAW


class TestRiichiFuriten:
    def test_riichi_furiten__when_riichi_player_discarded_winning_tile__should_flag_riichi_furiten(self):
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        furiten_discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(
                seat=1,
                tiles=hand_tiles_1,
                is_riichi=True,
                discards=(Discard(tile_id=furiten_discard_tile),),
            ),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
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
        assert new_round.players[1].is_riichi_furiten is True

    def test_riichi_furiten__when_riichi_player_not_furiten__should_offer_ron_prompt(self):
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=hand_tiles_1, is_riichi=True),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
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
        assert new_round.pending_call_prompt is not None
        assert new_round.pending_call_prompt.callers == (Caller(seat=1, can_ron=True),)
        assert new_round.players[1].is_riichi_furiten is False


class TestChiOpportunity:
    def test_chi_opportunity__when_next_player_holds_sequence__should_be_found(self):
        chi_tiles = TilesConverter.string_to_136_array(man="34")
        other_tiles = TilesConverter.string_to_136_array(pin="13579", sou="135799")
        hand_tiles_1 = (*chi_tiles, *other_tiles)
        discard_tile = TilesConverter.string_to_136_array(man="5")[0]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=hand_tiles_1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="6666"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="22224444666688"))
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
        prompt = new_round.pending_call_prompt
        assert prompt is not None
        assert [c.seat for c in prompt.callers] == [1]
        assert [m.call_type for m in prompt.caller(1).melds] == [MeldCallType.CHI]


class TestFindRonCallers:
    def test_find_ron_callers__when_player_tenpai_on_discard__should_include_player(self):
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=hand_tiles_1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
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
        assert new_round.pending_call_prompt is not None
        assert new_round.pending_call_prompt.callers == (Caller(seat=1, can_ron=True),)

    def test_find_ron_callers__when_multiple_callers__should_sort_by_distance(self):
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=hand_tiles),
            create_player(seat=2),
            create_player(seat=3, tiles=hand_tiles),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
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
        assert new_round.pending_call_prompt is not None
        assert [c.seat for c in new_round.pending_call_prompt.callers if c.can_ron] == [1, 3]


class TestSingleRonHandError:
    def test_single_ron__when_hand_result_error__should_raise(self):
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0),
            create_player(seat=1, tiles=hand_tiles_1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        with patch("game.logic.turn.calculate_hand_value_with_tiles") as mock_calc:
            mock_calc.return_value = HandResult(error="mock error")

            ron_input = RonCallInput(ron_callers=[1], tile_id=discard_tile, discarder_seat=0)
            with pytest.raises(ScoringError, match="ron calculation error"):
                process_ron_call(game_state, ron_input=ron_input)


class TestDoubleRonHandError:
    def test_double_ron__when_second_winner_scoring_fails__should_raise_scoring_error_blaming_nobody(self):
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0),
            create_player(seat=1, tiles=hand_tiles),
            create_player(seat=2, tiles=hand_tiles),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        first_winner_already_called_ron = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({2}),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True)),
            responses=(CallResponse(seat=1, action=GameAction.CALL_RON),),
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=first_winner_already_called_ron,
        )
        game_state = create_game_state(round_state)

        def fail_for_second_winner(ctx: ScoringContext, *, tiles: list[int], win_tile: int) -> HandResult:
            if ctx.player.seat == 2:
                return HandResult(error="mock error")

            return calculate_hand_value_with_tiles(ctx, tiles=tiles, win_tile=win_tile)

        with (
            patch("game.logic.turn.calculate_hand_value_with_tiles", side_effect=fail_for_second_winner),
            pytest.raises(ScoringError, match="ron calculation error for seat 2"),
        ):
            handle_ron(game_state, seat=2)


class TestTsumoHandError:
    def test_tsumo__when_scoring_library_fails__should_raise_scoring_error_not_kick(self):
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="12355"))
        players = (
            create_player(seat=0, tiles=hand_tiles),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        with patch("game.logic.turn.calculate_hand_value") as mock_calc:
            mock_calc.return_value = HandResult(error="mock error")

            with pytest.raises(ScoringError, match="tsumo calculation error"):
                handle_tsumo(game_state, seat=0)


class TestAddedKanChankan:
    def test_added_kan__when_player_can_chankan__should_prompt_chankan(self):
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
            who=0,
        )
        fourth_tile = TilesConverter.string_to_136_array(man="1111")[3]
        other_tiles_0 = TilesConverter.string_to_136_array(pin="123456789", sou="11")
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="23456789", pin="456", sou="55"))
        players = (
            create_player(seat=0, tiles=(fourth_tile, *other_tiles_0), melds=(pon_meld,)),
            create_player(seat=1, tiles=hand_tiles_1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="22223333444466"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        meld_input = MeldCallInput(caller_seat=0, call_type=MeldCallType.ADDED_KAN, tile_id=fourth_tile)
        _new_game, events = process_meld_call(game_state, meld_input=meld_input)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.CHANKAN]
        assert len(call_prompts) == 1


class TestChiSequenceTilesValidation:
    def test_chi__when_sequence_tiles_none__should_raise(self):
        chi_tiles = TilesConverter.string_to_136_array(man="34")
        other_tiles = TilesConverter.string_to_136_array(pin="123456789", sou="11")
        hand_tiles_1 = (*chi_tiles, *other_tiles)
        discard_tile = TilesConverter.string_to_136_array(man="5")[0]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=hand_tiles_1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="6666"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="22223333444466"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        meld_input = MeldCallInput(
            caller_seat=1,
            call_type=MeldCallType.CHI,
            tile_id=discard_tile,
            sequence_tiles=None,
        )
        with pytest.raises(AssertionError, match="chi call requires sequence_tiles"):
            process_meld_call(game_state, meld_input=meld_input)


class TestAbortiveDrawIntegration:
    def test_abortive_draw__when_four_same_winds_discarded__should_abort_four_winds(self):
        east_winds = tuple(TilesConverter.string_to_136_array(honors="1111"))
        discard_tile = east_winds[3]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            all_discards=east_winds[:3],
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_discard_phase(game_state, discard_tile)
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_WINDS

    def test_abortive_draw__when_three_players_ron__should_abort_triple_ron(self):
        tenpai_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0, tiles=(discard_tile,)),
            create_player(seat=1, tiles=tenpai_hand),
            create_player(seat=2, tiles=tenpai_hand),
            create_player(seat=3, tiles=tenpai_hand),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_discard_phase(game_state, discard_tile)
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.TRIPLE_RON

    def test_abortive_draw__when_four_players_riichi__should_abort_four_riichi(self):
        hand_tiles_0 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113", sou="5"))
        discard_tile = TilesConverter.string_to_136_array(sou="5")[0]
        players = (
            create_player(seat=0, tiles=hand_tiles_0),
            create_player(seat=1, is_riichi=True),
            create_player(seat=2, is_riichi=True),
            create_player(seat=3, is_riichi=True),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333366"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_game, events = process_discard_phase(
            game_state,
            discard_tile,
            is_riichi=True,
        )
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI


class TestDoubleRonScenario:
    def test_double_ron__when_two_players_ron__should_produce_double_ron_result(self):
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        players = (
            create_player(seat=0),
            create_player(seat=1, tiles=hand_tiles),
            create_player(seat=2, tiles=hand_tiles),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        ron_input = RonCallInput(ron_callers=[1, 2], tile_id=discard_tile, discarder_seat=0)
        _new_game, events = process_ron_call(game_state, ron_input=ron_input)
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestAddedKanNormalPath:
    def test_added_kan__when_no_chankan__should_upgrade_pon_to_shouminkan(self):
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
            who=0,
        )
        fourth_tile = TilesConverter.string_to_136_array(man="1111")[3]
        other_tiles = TilesConverter.string_to_136_array(pin="123456789", sou="11")
        players = (
            create_player(seat=0, tiles=(fourth_tile, *other_tiles), melds=(pon_meld,)),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="22223333444466"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        meld_input = MeldCallInput(caller_seat=0, call_type=MeldCallType.ADDED_KAN, tile_id=fourth_tile)
        new_game, _events = process_meld_call(game_state, meld_input=meld_input)
        new_round = new_game.round_state
        assert any(m.type == FrozenMeld.SHOUMINKAN for m in new_round.players[0].melds)


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


class TestValidateRiichiDiscard:
    def test_validate_riichi_discard__when_discard_breaks_tenpai__should_reject(self):
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113", sou="5"))
        bad_discard = TilesConverter.string_to_136_array(pin="1")[0]
        player = create_player(seat=0, tiles=hand_tiles)

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333366"))
        round_state = create_round_state(
            players=(player, *(create_player(seat=i) for i in range(1, 4))),
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        with pytest.raises(InvalidRiichiError, match="not tenpai"):
            _validate_riichi_discard(player, round_state, tile_id=bad_discard, settings=GameSettings())
