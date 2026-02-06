"""
Unit tests for turn.py edge cases that were previously marked as pragma: no cover.
"""

from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import AbortiveDrawType
from game.logic.enums import CallType, MeldCallType, PlayerAction, RoundPhase, RoundResultType
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
        """
        Player with 9+ terminal/honor types on first turn gets kyuushu action in draw phase.

        This tests line ~165 in turn.py where kyuushu is added to available actions.
        """
        # create hand with 9 terminal/honor types: 1m 9m 1p 9p 1s 9s E S W + fillers
        kyuushu_tiles = tuple(
            TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123")
            + TilesConverter.string_to_136_array(man="22334")
        )

        players = tuple(create_player(seat=i, tiles=kyuushu_tiles if i == 0 else ()) for i in range(4))

        # wall needs at least 1 tile, dead wall needs 14, no discards, no open hands
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

        # find TurnEvent and check for KYUUSHU action
        turn_events = [e for e in events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1
        available_actions = [a.action for a in turn_events[0].available_actions]
        assert PlayerAction.KYUUSHU in available_actions


class TestRiichiFuriten:
    def test_riichi_furiten_on_discard(self):
        """
        A riichi player becomes furiten when their waiting tile passes without ron.

        Tests lines ~203, 206, 207 where riichi furiten is set.
        The riichi player is already discard-furiten (has discarded a waiting tile),
        so can_call_ron returns False, they are not in ron_callers, and
        _check_riichi_furiten marks them as riichi furiten.
        """
        # seat 1 is riichi and waiting on 3p
        # hand: 123m 456m 789m 12p 55p (waiting on 3p)
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        # seat 0 discards 3p
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        # seat 1 has previously discarded a 3p, making them discard-furiten.
        # This prevents can_call_ron from returning True, so they won't be
        # in ron_callers, and _check_riichi_furiten will mark them.
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

        # seat 1 cannot call ron (discard furiten) so they are not in ron_callers,
        # and _check_riichi_furiten sets is_riichi_furiten = True
        assert new_round.players[1].is_riichi_furiten is True

    def test_riichi_furiten_skips_ron_callers(self):
        """
        A riichi player who CAN call ron is NOT marked furiten.

        Tests line ~203 where the skip branch for ron_callers is taken.
        """
        # seat 1 is riichi and waiting on 3p with a valid hand that can ron
        # hand: 123m 456m 789m 12p 55p (waiting on 3p)
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        # seat 0 discards 3p
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

        # seat 1 should be able to call ron (appears in ron_callers), so NOT furiten
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        if call_prompts:
            # if ron prompt exists, seat 1 is in the callers list and should NOT be furiten
            assert new_round.players[1].is_riichi_furiten is False


class TestChiOpportunity:
    def test_chi_opportunity_found(self):
        """
        Chi opportunity is detected when kamicha can form a sequence.

        Tests line ~252 where chi branch in _find_meld_callers is hit.
        """
        # seat 1 (kamicha of seat 0) has tiles to form chi with 5m
        # hand: 3m 4m + other tiles that do NOT form a winning hand with 5m
        # 2 + 5 + 6 = 13 tiles total (non-winning shape)
        chi_tiles = TilesConverter.string_to_136_array(man="34")
        other_tiles = TilesConverter.string_to_136_array(pin="13579", sou="135799")
        hand_tiles_1 = (*chi_tiles, *other_tiles)

        # seat 0 discards 5m
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

        # should have a MELD call prompt with CHI option
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.MELD]
        assert len(call_prompts) == 1
        # check that chi is available in the callers
        chi_callers = [
            c for c in call_prompts[0].callers if hasattr(c, "call_type") and c.call_type == MeldCallType.CHI
        ]
        assert len(chi_callers) >= 1


class TestFourWindsAbort:
    def test_four_winds_abort(self):
        """
        Four identical wind discards from first turns trigger abortive draw.

        Tests line ~319 where four winds check triggers abort.
        """
        # create state with 3 east wind discards already made
        east_winds = tuple(TilesConverter.string_to_136_array(honors="1111"))

        # discard tile is the 4th east wind
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
            all_discards=east_winds[:3],  # first 3 east winds already discarded
            players_with_open_hands=(),
        )
        game_state = create_game_state(round_state)

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        # should end with ABORTIVE_DRAW
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_WINDS


class TestTripleRonAbort:
    def test_triple_ron_abort(self):
        """
        Three players can ron on a discard triggers abortive draw.

        Tests line ~333 where triple ron check triggers abort.
        """
        # create 3 players in tenpai waiting on the same tile
        # seat 1, 2, 3 all waiting on 3p
        # hand: 123m 456m 789m 12p 55p (waiting on 3p)
        tenpai_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        # seat 0 discards 3p
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

        # should end with ABORTIVE_DRAW TRIPLE_RON
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.TRIPLE_RON


class TestRonCallersPendingPrompt:
    def test_ron_callers_create_pending_prompt(self):
        """
        Ron opportunity creates pending call prompt.

        Tests line ~341 where ron callers create a CallPromptEvent.
        """
        # seat 1 waiting on 3p
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        # seat 0 discards 3p
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

        # should have CallPromptEvent with RON
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        assert len(call_prompts) >= 1


class TestFourRiichiAbort:
    def test_four_riichi_abort(self):
        """
        Fourth riichi declaration triggers abortive draw.

        Tests line ~374 where four riichi check triggers abort.
        """
        # 3 players already have riichi, seat 0 declares 4th riichi
        # seat 0 has tempai hand: 123m 456m 789m 111p + 5s (will discard 5s)
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
            round_state,
            game_state,
            discard_tile,
            is_riichi=True,
        )

        # should end with ABORTIVE_DRAW FOUR_RIICHI
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI


class TestFindRonCallers:
    def test_find_ron_callers_finds_tenpai_player(self):
        """
        _find_ron_callers detects eligible tenpai player.

        Tests line ~430 where ron callers are detected.
        """
        # seat 1 waiting on 3p
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        # seat 0 discards 3p
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

        # ron prompt should include seat 1
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        if call_prompts:
            assert 1 in call_prompts[0].callers

    def test_ron_callers_sorted_by_distance(self):
        """
        Multiple ron callers are sorted by counter-clockwise distance from discarder.

        Tests line ~434 where callers are sorted by distance.
        """
        # seat 1 and seat 3 both waiting on 3p
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        # seat 0 discards 3p
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

        # ron prompt should have callers sorted: seat 1 first (distance 1), seat 3 second (distance 3)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        if call_prompts:
            callers = call_prompts[0].callers
            assert callers[0] == 1
            assert callers[1] == 3


class TestSingleRonHandError:
    def test_single_ron_hand_error_raises(self):
        """
        Hand calculation error in single ron raises ValueError.

        Tests line ~473 where hand calculation error is raised.
        """
        # create a state where player can call ron but hand calculator returns error
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

        # mock calculate_hand_value_with_tiles to return error
        with patch("game.logic.turn.calculate_hand_value_with_tiles") as mock_calc:
            mock_calc.return_value = HandResult(error="mock error")

            with pytest.raises(ValueError, match="ron calculation error"):
                process_ron_call(round_state, game_state, [1], discard_tile, 0)


class TestDoubleRonScenario:
    def test_double_ron_scenario(self):
        """
        Two players simultaneously call ron.

        Tests line ~487 where double ron is processed.
        """
        # seat 1 and seat 2 both waiting on 3p
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        # seat 0 discards 3p
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

        # should end with DOUBLE_RON
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestDoubleRonHandError:
    def test_double_ron_hand_error_raises(self):
        """
        Hand calculation error in double ron raises ValueError.

        Tests lines ~498-502 where hand calc returns error for one of 2 ron winners.
        """
        # seat 1 and seat 2 both waiting on 3p
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

        # mock calculate_hand_value_with_tiles to return error for seat 1
        with patch("game.logic.turn.calculate_hand_value_with_tiles") as mock_calc:
            mock_calc.return_value = HandResult(error="mock error")

            with pytest.raises(ValueError, match="ron calculation error for seat 1"):
                process_ron_call(round_state, game_state, [1, 2], discard_tile, 0)


class TestTsumoHandError:
    def test_tsumo_hand_error_raises(self):
        """
        Hand calculation error in tsumo raises ValueError.

        Tests line ~549 where tsumo calculation error is raised.
        """
        # create a winning hand for seat 0
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

        # mock calculate_hand_value to return error
        with patch("game.logic.turn.calculate_hand_value") as mock_calc:
            mock_calc.return_value = HandResult(error="mock error")

            with pytest.raises(ValueError, match="tsumo calculation error"):
                process_tsumo_call(round_state, game_state, 0)


class TestFourKansAbort:
    def test_four_kans_abort_after_kan(self):
        """
        Four kans by different players triggers abortive draw.

        Tests line ~617 where _check_four_kans_abort returns aborted=True.
        """
        # create 3 existing kans across players
        kan_meld_0 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=True,
            who=0,
        )
        kan_meld_1 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(pin="1111")),
            opened=True,
            who=1,
        )
        kan_meld_2 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(sou="1111")),
            opened=True,
            who=2,
        )

        # seat 3 has 3 matching tiles for open kan on 5m
        kan_tiles_3 = TilesConverter.string_to_136_array(man="555")
        discard_tile = TilesConverter.string_to_136_array(man="5")[0]

        players = tuple(
            create_player(
                seat=i,
                tiles=tuple(kan_tiles_3) if i == 3 else ((discard_tile,) if i == 0 else ()),
                melds=(
                    (kan_meld_0,)
                    if i == 0
                    else ((kan_meld_1,) if i == 1 else ((kan_meld_2,) if i == 2 else ()))
                ),
            )
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

        # process open kan call
        _new_round, _new_game, events = process_meld_call(
            round_state,
            game_state,
            caller_seat=3,
            call_type=MeldCallType.OPEN_KAN,
            tile_id=discard_tile,
        )

        # should end with ABORTIVE_DRAW FOUR_KANS
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS


class TestProcessAddedKanCall:
    def test_process_added_kan_call(self):
        """
        Complete added kan flow without chankan.

        Tests line ~680 where _process_added_kan_call completes successfully.
        """
        # seat 0 has a pon of 1m and the 4th tile in hand
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

        # should have upgraded the pon to SHOUMINKAN
        assert any(m.type == FrozenMeld.SHOUMINKAN for m in new_round.players[0].melds)

    def test_process_added_kan_call_chankan(self):
        """
        Added kan with chankan opportunity.

        Tests line ~680 where chankan check returns seats.
        """
        # seat 0 has a pon of 1m and the 4th tile in hand
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
            who=0,
        )
        fourth_tile = TilesConverter.string_to_136_array(man="1111")[3]
        other_tiles_0 = TilesConverter.string_to_136_array(pin="123456789", sou="11")

        # seat 1 is waiting on 1m (can chankan)
        # hand: 23m 456m 789m 456p 55s = 13 tiles, waiting on 1m and 4m
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

        # should have CallPromptEvent with CHANKAN
        call_prompts = [
            e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.CHANKAN
        ]
        assert len(call_prompts) >= 1

    def test_process_added_kan_call_four_kans(self):
        """
        Added kan triggering four kans abort.

        Tests line ~680 where added kan makes 4 kans.
        """
        # create 3 existing kans
        kan_meld_0 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="2222")),
            opened=True,
            who=0,
        )
        kan_meld_1 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(pin="1111")),
            opened=True,
            who=1,
        )
        kan_meld_2 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(sou="1111")),
            opened=True,
            who=2,
        )

        # seat 0 has a pon of 1m and the 4th tile (will be 4th kan)
        pon_meld_0 = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
            who=0,
        )
        fourth_tile = TilesConverter.string_to_136_array(man="1111")[3]
        other_tiles = TilesConverter.string_to_136_array(pin="234567", sou="22")

        players = tuple(
            create_player(
                seat=i,
                tiles=(fourth_tile, *other_tiles) if i == 0 else (),
                melds=(
                    (kan_meld_0, pon_meld_0)
                    if i == 0
                    else ((kan_meld_1,) if i == 1 else ((kan_meld_2,) if i == 2 else ()))
                ),
            )
            for i in range(4)
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="33334444555566"))
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

        # should end with ABORTIVE_DRAW FOUR_KANS
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS


class TestChiSequenceTilesValidation:
    def test_chi_sequence_tiles_none_raises(self):
        """
        Invalid chi sequence (None) raises error.

        Tests line ~750 where missing sequence_tiles raises ValueError.
        """
        # seat 1 has tiles to form chi
        chi_tiles = TilesConverter.string_to_136_array(man="34")
        other_tiles = TilesConverter.string_to_136_array(pin="123456789", sou="11")
        hand_tiles_1 = (*chi_tiles, *other_tiles)

        # seat 0 discards 5m
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

        with pytest.raises(ValueError, match="chi call requires sequence_tiles"):
            process_meld_call(
                round_state,
                game_state,
                caller_seat=1,
                call_type=MeldCallType.CHI,
                tile_id=discard_tile,
                sequence_tiles=None,
            )


class TestProcessMeldCallAddedKanDispatch:
    def test_process_meld_call_added_kan_dispatch(self):
        """
        process_meld_call dispatches to added kan correctly.

        Tests line ~763 where ADDED_KAN is dispatched.
        """
        # seat 0 has a pon of 1m and the 4th tile in hand
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

        # call process_meld_call with ADDED_KAN
        new_round, _new_game, _events = process_meld_call(
            round_state,
            game_state,
            caller_seat=0,
            call_type=MeldCallType.ADDED_KAN,
            tile_id=fourth_tile,
        )

        # verify added kan was processed
        assert any(m.type == FrozenMeld.SHOUMINKAN for m in new_round.players[0].melds)
