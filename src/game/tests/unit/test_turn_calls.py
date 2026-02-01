"""
Unit tests for turn loop meld/ron/tsumo call processing.
"""

from unittest.mock import patch

import pytest
from mahjong.meld import Meld as MahjongMeld
from mahjong.tile import TilesConverter

from game.logic.enums import MeldCallType, MeldViewType
from game.logic.game import init_game
from game.logic.scoring import HandResult
from game.logic.state import RoundPhase
from game.logic.turn import (
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.messaging.events import MeldEvent, RoundEndEvent
from game.tests.unit.helpers import _default_seat_configs


class TestProcessMeldCall:
    def _create_game_state_with_pon_opportunity(self):
        """Create a game state where player 1 can pon a discarded tile."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 two 1m tiles (tiles 0-3 are all 1m)
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="11", pin="12345", sou="123456")

        # player 0 will discard another 1m
        tile_to_pon = TilesConverter.string_to_136_array(man="111")[2]
        round_state.players[0].tiles.append(tile_to_pon)
        round_state.current_player_seat = 0

        return game_state, tile_to_pon

    def test_process_pon_call(self):
        game_state, tile_to_pon = self._create_game_state_with_pon_opportunity()
        round_state = game_state.round_state

        events = process_meld_call(
            round_state, game_state, caller_seat=1, call_type=MeldCallType.PON, tile_id=tile_to_pon
        )

        meld_events = [e for e in events if e.type == "meld"]
        assert len(meld_events) == 1
        assert isinstance(meld_events[0], MeldEvent)
        assert meld_events[0].meld_type == MeldViewType.PON
        assert meld_events[0].caller_seat == 1
        assert meld_events[0].from_seat == 0
        assert round_state.current_player_seat == 1

    def test_process_chi_call(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 1 has 2m and 3m tiles (can chi 1m from player 0)
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="236789", pin="2345789")

        # player 0 discards 1m
        round_state.current_player_seat = 0
        tile_to_chi = TilesConverter.string_to_136_array(man="1")[0]

        # chi requires sequence_tiles
        tile_2m = TilesConverter.string_to_136_array(man="2")[0]
        tile_3m = TilesConverter.string_to_136_array(man="3")[0]
        events = process_meld_call(
            round_state,
            game_state,
            caller_seat=1,
            call_type=MeldCallType.CHI,
            tile_id=tile_to_chi,
            sequence_tiles=(tile_2m, tile_3m),
        )

        meld_events = [e for e in events if e.type == "meld"]
        assert len(meld_events) == 1
        assert isinstance(meld_events[0], MeldEvent)
        assert meld_events[0].meld_type == MeldViewType.CHI
        assert meld_events[0].caller_seat == 1
        assert round_state.current_player_seat == 1

    def test_process_chi_call_requires_sequence_tiles(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        round_state.current_player_seat = 0

        tile_1m = TilesConverter.string_to_136_array(man="1")[0]
        with pytest.raises(ValueError, match="chi call requires sequence_tiles"):
            process_meld_call(
                round_state, game_state, caller_seat=1, call_type=MeldCallType.CHI, tile_id=tile_1m
            )


class TestProcessRonCall:
    def _create_game_state_with_ron_opportunity(self):
        """Create a game state where player 1 can ron on player 0's discard."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a winning hand (needs one tile to complete)
        # complete hand: 123m 456m 789m 111p 22p
        # waiting for 2p
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")

        # player 0 has the winning tile (2nd copy of 2p)
        win_tile = TilesConverter.string_to_136_array(pin="22")[1]
        round_state.players[0].tiles.append(win_tile)
        round_state.current_player_seat = 0

        return game_state, win_tile, 0  # discarder_seat

    def test_process_single_ron(self):
        game_state, win_tile, discarder_seat = self._create_game_state_with_ron_opportunity()
        round_state = game_state.round_state

        events = process_ron_call(
            round_state, game_state, ron_callers=[1], tile_id=win_tile, discarder_seat=discarder_seat
        )

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        result = round_end_events[0].result
        assert result.type == "ron"
        assert result.winner_seat == 1
        assert result.loser_seat == 0
        assert round_state.phase == RoundPhase.FINISHED


class TestProcessRonCallOpenHand:
    """Tests ron call with open hand where meld tiles are removed from player.tiles."""

    def test_process_ron_with_open_pon_meld_tiles_removed(self):
        """Ron succeeds when meld tiles are not in player.tiles (actual gameplay state)."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # simulate actual gameplay: player 1 called pon earlier
        # closed: 234m 567m 23s 55s (10 tiles) + PON(Haku) (meld)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = MahjongMeld(
            meld_type=MahjongMeld.PON,
            tiles=haku_tiles,
            opened=True,
            called_tile=haku_tiles[0],
            who=1,
            from_who=2,
        )

        # only closed tiles in player.tiles (meld tiles removed, matching actual gameplay)
        round_state.players[1].tiles = closed_tiles
        round_state.players[1].melds = [pon]
        round_state.players_with_open_hands = [1]

        # 4s completes the hand: 234m 567m 234s 55s + PON(Haku)
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        round_state.current_player_seat = 0

        events = process_ron_call(
            round_state, game_state, ron_callers=[1], tile_id=win_tile, discarder_seat=0
        )

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        result = round_end_events[0].result
        assert result.type == "ron"
        assert result.winner_seat == 1
        assert result.loser_seat == 0
        assert round_state.phase == RoundPhase.FINISHED


class TestProcessTsumoCall:
    def _create_game_state_with_tsumo(self):
        """Create a game state where player 0 has a winning hand."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 a complete winning hand (14 tiles)
        # 123m 456m 789m 111p 22p
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="11122")

        return game_state

    def test_process_tsumo(self):
        game_state = self._create_game_state_with_tsumo()
        round_state = game_state.round_state

        events = process_tsumo_call(round_state, game_state, winner_seat=0)

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        result = round_end_events[0].result
        assert result.type == "tsumo"
        assert result.winner_seat == 0
        assert round_state.phase == RoundPhase.FINISHED

    def test_process_tsumo_clears_pending_dora(self):
        game_state = self._create_game_state_with_tsumo()
        round_state = game_state.round_state
        # simulate pending dora from open/added kan
        round_state.pending_dora_count = 1

        process_tsumo_call(round_state, game_state, winner_seat=0)

        # tsumo win clears pending dora (not revealed for the winning hand)
        assert round_state.pending_dora_count == 0


class TestOpenKanMeldCall:
    """Tests open kan meld call processing."""

    def test_process_open_kan_call(self):
        """Process open kan creates meld event with kan type."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 three 1m tiles plus other tiles
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="111", pin="23456", sou="23456")

        tile_to_kan = TilesConverter.string_to_136_array(man="1111")[3]  # 4th 1m tile
        round_state.current_player_seat = 0

        events = process_meld_call(
            round_state,
            game_state,
            caller_seat=1,
            call_type=MeldCallType.OPEN_KAN,
            tile_id=tile_to_kan,
        )

        meld_events = [e for e in events if e.type == "meld"]
        assert len(meld_events) == 1
        assert isinstance(meld_events[0], MeldEvent)
        assert meld_events[0].meld_type == MeldViewType.KAN
        assert meld_events[0].kan_type == "open"


class TestClosedKanMeldCall:
    """Tests closed kan meld call processing."""

    def test_process_closed_kan_call(self):
        """Process closed kan creates meld event."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 four 1m tiles plus other tiles
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="1111", pin="2345", sou="23456")
        round_state.current_player_seat = 0

        events = process_meld_call(
            round_state,
            game_state,
            caller_seat=0,
            call_type=MeldCallType.CLOSED_KAN,
            tile_id=TilesConverter.string_to_136_array(man="1")[0],
        )

        meld_events = [e for e in events if e.type == "meld"]
        assert len(meld_events) == 1
        assert isinstance(meld_events[0], MeldEvent)
        assert meld_events[0].meld_type == MeldViewType.KAN
        assert meld_events[0].kan_type == "closed"


class TestAddedKanMeldCall:
    """Tests added kan meld call processing."""

    def test_process_added_kan_call(self):
        """Process added kan upgrades pon to kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[0]

        # give player a pon meld and the 4th tile in hand
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        fourth_1m = TilesConverter.string_to_136_array(man="1111")[3]
        pon_meld = MahjongMeld(
            meld_type=MahjongMeld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=pon_tiles[2],
            who=0,
            from_who=1,
        )
        player.melds = [pon_meld]
        player.tiles = [fourth_1m, *TilesConverter.string_to_136_array(pin="12345", sou="1234567")]
        round_state.current_player_seat = 0
        round_state.players_with_open_hands = [0]

        events = process_meld_call(
            round_state,
            game_state,
            caller_seat=0,
            call_type=MeldCallType.ADDED_KAN,
            tile_id=fourth_1m,
        )

        # should produce at least one event (meld event or chankan prompt)
        assert len(events) > 0
        meld_events = [e for e in events if e.type == "meld"]
        chankan_prompts = [e for e in events if e.type == "call_prompt"]
        assert len(meld_events) > 0 or len(chankan_prompts) > 0


class TestProcessMeldCallUnknownType:
    """Tests unknown meld call type raises ValueError."""

    def test_unknown_call_type_raises_value_error(self):
        """Passing an unknown call_type to process_meld_call raises ValueError."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_1m = TilesConverter.string_to_136_array(man="1")[0]
        with pytest.raises(ValueError, match="unknown call_type"):
            process_meld_call(
                round_state,
                game_state,
                caller_seat=0,
                call_type="invalid_type",  # type: ignore[arg-type]
                tile_id=tile_1m,
            )


class TestProcessRonCallHandError:
    """Tests ron call handling when hand calculation returns an error."""

    def test_single_ron_hand_error_raises(self):
        """Single ron with hand calculation error raises ValueError."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a waiting hand
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]  # 2nd copy of 2p
        round_state.current_player_seat = 0

        error_result = HandResult(error="test error")
        with (
            patch("game.logic.turn.calculate_hand_value", return_value=error_result),
            pytest.raises(ValueError, match="ron calculation error"),
        ):
            process_ron_call(round_state, game_state, [1], win_tile, 0)

    def test_double_ron_hand_error_raises(self):
        """Double ron with hand calculation error raises ValueError."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        waiting_hand = TilesConverter.string_to_136_array(man="123456789", pin="1112")
        round_state.players[1].tiles = list(waiting_hand)
        round_state.players[2].tiles = list(waiting_hand)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]  # 2nd copy of 2p
        round_state.current_player_seat = 0

        error_result = HandResult(error="test error")
        with (
            patch("game.logic.turn.calculate_hand_value", return_value=error_result),
            pytest.raises(ValueError, match="ron calculation error"),
        ):
            process_ron_call(round_state, game_state, [1, 2], win_tile, 0)


class TestProcessTsumoCallHandError:
    """Tests tsumo call handling when hand calculation returns an error."""

    def test_tsumo_hand_error_raises(self):
        """Tsumo with hand calculation error raises ValueError."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 a complete winning hand (14 tiles)
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="11122")

        error_result = HandResult(error="test error")
        with (
            patch("game.logic.turn.calculate_hand_value", return_value=error_result),
            pytest.raises(ValueError, match="tsumo calculation error"),
        ):
            process_tsumo_call(round_state, game_state, 0)
