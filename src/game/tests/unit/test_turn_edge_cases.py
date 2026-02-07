"""
Unit tests for turn.py edge cases requiring direct state construction.

Covers: kyuushu availability in draw phase, riichi furiten marking logic,
chi opportunity detection via _find_meld_callers, ron caller detection and
distance sorting, hand calculation error paths for single ron / double ron / tsumo,
chankan opportunity detection via _process_added_kan_call, and chi sequence_tiles
validation in process_meld_call.
"""

from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import AbortiveDrawType
from game.logic.enums import CallType, MeldCallType, PlayerAction, RoundPhase, RoundResultType
from game.logic.exceptions import InvalidMeldError, InvalidWinError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import HandResult
from game.logic.state import Discard
from game.logic.turn import (
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.messaging.events import CallPromptEvent, RoundEndEvent, TurnEvent
from game.tests.conftest import create_game_state, create_player, create_round_state


class TestKyuushuKyuuhaiDrawPhase:
    def test_kyuushu_kyuuhai_available_in_draw_phase(self):
        """Player with 9+ terminal/honor types on first turn gets kyuushu action."""
        kyuushu_tiles = tuple(
            TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123")
            + TilesConverter.string_to_136_array(man="22334")
        )

        players = tuple(create_player(seat=i, tiles=kyuushu_tiles if i == 0 else ()) for i in range(4))

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
            players_with_open_hands=(),
        )
        game_state = create_game_state(round_state)

        _new_round, _new_game, events = process_draw_phase(round_state, game_state)

        turn_events = [e for e in events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1
        available_actions = [a.action for a in turn_events[0].available_actions]
        assert PlayerAction.KYUUSHU in available_actions


class TestRiichiFuriten:
    def test_riichi_furiten_on_discard(self):
        """Riichi player becomes furiten when their waiting tile passes without ron."""
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        furiten_discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(
            create_player(
                seat=i,
                tiles=hand_tiles_1 if i == 1 else ((discard_tile,) if i == 0 else ()),
                is_riichi=(i == 1),
                discards=(Discard(tile_id=furiten_discard_tile),) if i == 1 else (),
            )
            for i in range(4)
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

        new_round, _new_game, _events = process_discard_phase(round_state, game_state, discard_tile)

        assert new_round.players[1].is_riichi_furiten is True

    def test_riichi_furiten_skips_ron_callers(self):
        """Riichi player who CAN call ron is NOT marked furiten."""
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(
            create_player(
                seat=i,
                tiles=hand_tiles_1 if i == 1 else ((discard_tile,) if i == 0 else ()),
                is_riichi=(i == 1),
            )
            for i in range(4)
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

        new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        assert len(call_prompts) >= 1
        assert new_round.players[1].is_riichi_furiten is False


class TestChiOpportunity:
    def test_chi_opportunity_found(self):
        """Chi opportunity is detected when kamicha can form a sequence."""
        chi_tiles = TilesConverter.string_to_136_array(man="34")
        other_tiles = TilesConverter.string_to_136_array(pin="13579", sou="135799")
        hand_tiles_1 = (*chi_tiles, *other_tiles)

        discard_tile = TilesConverter.string_to_136_array(man="5")[0]

        players = tuple(
            create_player(seat=i, tiles=hand_tiles_1 if i == 1 else ((discard_tile,) if i == 0 else ()))
            for i in range(4)
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

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.MELD]
        assert len(call_prompts) == 1
        chi_callers = [
            c for c in call_prompts[0].callers if hasattr(c, "call_type") and c.call_type == MeldCallType.CHI
        ]
        assert len(chi_callers) >= 1


class TestFindRonCallers:
    def test_find_ron_callers_finds_tenpai_player(self):
        """_find_ron_callers detects eligible tenpai player."""
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(
            create_player(seat=i, tiles=hand_tiles_1 if i == 1 else ((discard_tile,) if i == 0 else ()))
            for i in range(4)
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

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        assert len(call_prompts) >= 1
        assert 1 in call_prompts[0].callers

    def test_ron_callers_sorted_by_distance(self):
        """Multiple ron callers are sorted by counter-clockwise distance from discarder."""
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(
            create_player(seat=i, tiles=hand_tiles if i in (1, 3) else ((discard_tile,) if i == 0 else ()))
            for i in range(4)
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

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        assert len(call_prompts) >= 1
        callers = call_prompts[0].callers
        assert callers[0] == 1
        assert callers[1] == 3


class TestSingleRonHandError:
    def test_single_ron_hand_error_raises(self):
        """Hand calculation error in single ron raises typed domain exception."""
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(create_player(seat=i, tiles=hand_tiles_1 if i == 1 else ()) for i in range(4))

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

            with pytest.raises(InvalidWinError, match="ron calculation error"):
                process_ron_call(round_state, game_state, [1], discard_tile, 0)


class TestDoubleRonHandError:
    def test_double_ron_hand_error_raises(self):
        """Hand calculation error in double ron raises InvalidWinError with seat number."""
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(create_player(seat=i, tiles=hand_tiles if i in (1, 2) else ()) for i in range(4))

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

            with pytest.raises(InvalidWinError, match="ron calculation error for seat 1"):
                process_ron_call(round_state, game_state, [1, 2], discard_tile, 0)


class TestTsumoHandError:
    def test_tsumo_hand_error_raises(self):
        """Hand calculation error in tsumo raises typed domain exception."""
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="12355"))

        players = tuple(create_player(seat=i, tiles=hand_tiles if i == 0 else ()) for i in range(4))

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

            with pytest.raises(InvalidWinError, match="tsumo calculation error"):
                process_tsumo_call(round_state, game_state, 0)


class TestAddedKanChankan:
    def test_process_added_kan_call_chankan(self):
        """Added kan with chankan opportunity creates CHANKAN call prompt."""
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
            who=0,
        )
        fourth_tile = TilesConverter.string_to_136_array(man="1111")[3]
        other_tiles_0 = TilesConverter.string_to_136_array(pin="123456789", sou="11")

        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="23456789", pin="456", sou="55"))

        players = tuple(
            create_player(
                seat=i,
                tiles=(fourth_tile, *other_tiles_0) if i == 0 else (hand_tiles_1 if i == 1 else ()),
                melds=(pon_meld,) if i == 0 else (),
            )
            for i in range(4)
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

        _new_round, _new_game, events = process_meld_call(
            round_state,
            game_state,
            caller_seat=0,
            call_type=MeldCallType.ADDED_KAN,
            tile_id=fourth_tile,
        )

        call_prompts = [
            e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.CHANKAN
        ]
        assert len(call_prompts) >= 1


class TestChiSequenceTilesValidation:
    def test_chi_sequence_tiles_none_raises(self):
        """Chi call with None sequence_tiles raises typed domain exception."""
        chi_tiles = TilesConverter.string_to_136_array(man="34")
        other_tiles = TilesConverter.string_to_136_array(pin="123456789", sou="11")
        hand_tiles_1 = (*chi_tiles, *other_tiles)

        discard_tile = TilesConverter.string_to_136_array(man="5")[0]

        players = tuple(
            create_player(seat=i, tiles=hand_tiles_1 if i == 1 else ((discard_tile,) if i == 0 else ()))
            for i in range(4)
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

        with pytest.raises(InvalidMeldError, match="chi call requires sequence_tiles"):
            process_meld_call(
                round_state,
                game_state,
                caller_seat=1,
                call_type=MeldCallType.CHI,
                tile_id=discard_tile,
                sequence_tiles=None,
            )


class TestAbortiveDrawIntegration:
    """Integration tests for abortive draw paths through process_discard_phase."""

    def test_four_winds_abort(self):
        """Four identical wind discards trigger abortive draw via process_discard_phase."""
        east_winds = tuple(TilesConverter.string_to_136_array(honors="1111"))
        discard_tile = east_winds[3]

        players = tuple(create_player(seat=i, tiles=(discard_tile,) if i == 0 else ()) for i in range(4))

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
            players_with_open_hands=(),
        )
        game_state = create_game_state(round_state)

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_WINDS

    def test_triple_ron_abort(self):
        """Three ron callers trigger abortive draw via process_discard_phase."""
        tenpai_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(
            create_player(
                seat=i, tiles=tenpai_hand if i in (1, 2, 3) else ((discard_tile,) if i == 0 else ())
            )
            for i in range(4)
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

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.TRIPLE_RON

    def test_four_riichi_abort(self):
        """Fourth riichi declaration triggers abortive draw via process_discard_phase."""
        hand_tiles_0 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113", sou="5"))
        discard_tile = TilesConverter.string_to_136_array(sou="5")[0]

        players = tuple(
            create_player(seat=i, tiles=hand_tiles_0 if i == 0 else (), is_riichi=(i in (1, 2, 3)))
            for i in range(4)
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

        _new_round, _new_game, events = process_discard_phase(
            round_state, game_state, discard_tile, is_riichi=True
        )

        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI


class TestDoubleRonScenario:
    def test_double_ron_produces_double_ron_result(self):
        """Two players simultaneously calling ron produces DOUBLE_RON result type."""
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        players = tuple(create_player(seat=i, tiles=hand_tiles if i in (1, 2) else ()) for i in range(4))

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

        _new_round, _new_game, events = process_ron_call(round_state, game_state, [1, 2], discard_tile, 0)

        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestAddedKanNormalPath:
    def test_added_kan_upgrades_pon_to_shouminkan(self):
        """Added kan without chankan upgrades pon to SHOUMINKAN."""
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
            who=0,
        )
        fourth_tile = TilesConverter.string_to_136_array(man="1111")[3]
        other_tiles = TilesConverter.string_to_136_array(pin="123456789", sou="11")

        players = tuple(
            create_player(
                seat=i,
                tiles=(fourth_tile, *other_tiles) if i == 0 else (),
                melds=(pon_meld,) if i == 0 else (),
            )
            for i in range(4)
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

        new_round, _new_game, _events = process_meld_call(
            round_state,
            game_state,
            caller_seat=0,
            call_type=MeldCallType.ADDED_KAN,
            tile_id=fourth_tile,
        )

        assert any(m.type == FrozenMeld.SHOUMINKAN for m in new_round.players[0].melds)
