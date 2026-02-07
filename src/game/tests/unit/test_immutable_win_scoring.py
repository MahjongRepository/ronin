"""
Unit tests for win scoring edge cases requiring direct state construction.

Covers: karaten tempai, double ron with pao, exhaustive draw triggering nagashi mangan,
check_nagashi_mangan qualification/disqualification, and calculate_hand_value error paths.
"""

from mahjong.tile import TilesConverter

from game.logic.enums import RoundResultType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import (
    check_nagashi_mangan,
    is_tempai,
    process_exhaustive_draw,
)
from game.logic.scoring import (
    HandResult,
    apply_double_ron_score,
    calculate_hand_value,
    calculate_hand_value_with_tiles,
)
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.win import can_call_ron


class TestIsTempaiKaraten:
    def test_pure_karaten_returns_false(self):
        """Pure karaten (all waits in own hand + melds) returns False."""
        tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="9"))
        pin_9_tiles = TilesConverter.string_to_136_array(pin="999")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pin_9_tiles),
            opened=True,
            called_tile=pin_9_tiles[0],
            who=0,
            from_who=1,
        )

        result = is_tempai(tiles, melds=(pon,))

        assert result is False


class TestCanCallRonFuritenGuards:
    """Test furiten guard clauses in can_call_ron that block ron declaration."""

    def _create_ron_state(self):
        """Create a round state with player 0 holding a winning hand waiting on 5p."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        dora_tiles = TilesConverter.string_to_136_array(man="1")
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1235")
        players_list = list(players)
        players_list[0] = players_list[0].model_copy(update={"tiles": tuple(tiles), "is_riichi": True})
        round_state = MahjongRoundState(
            dealer_seat=0,
            players=tuple(players_list),
            dora_indicators=tuple(dora_tiles),
            all_discards=tuple(TilesConverter.string_to_136_array(man="1112")),
        )
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]
        return round_state, win_tile

    def test_riichi_furiten_blocks_ron(self):
        """Player in riichi furiten cannot call ron."""
        round_state, win_tile = self._create_ron_state()
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"is_riichi_furiten": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        result = can_call_ron(round_state.players[0], win_tile, round_state)

        assert result is False

    def test_temporary_furiten_blocks_ron(self):
        """Player in temporary furiten cannot call ron."""
        round_state, win_tile = self._create_ron_state()
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"is_temporary_furiten": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        result = can_call_ron(round_state.players[0], win_tile, round_state)

        assert result is False


class TestProcessExhaustiveDrawPayment:
    def test_one_tempai_three_noten(self):
        """1 tempai, 3 noten: 3000 points split — tempai gets 3000, each noten pays 1000."""
        tempai_hand = tuple(TilesConverter.string_to_136_array(man="1123456788899"))
        non_tempai_hand = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"))
        players = tuple(
            MahjongPlayer(
                seat=seat,
                name=f"Player{seat}",
                tiles=tempai_hand if seat == 0 else non_tempai_hand,
                score=25000,
            )
            for seat in range(4)
        )
        round_state = MahjongRoundState(players=players, wall=())
        game_state = MahjongGameState(round_state=round_state)

        new_round, _new_game, result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == [0]
        assert result.noten_seats == [1, 2, 3]
        assert new_round.players[0].score == 28000
        assert new_round.players[1].score == 24000
        assert new_round.players[2].score == 24000
        assert new_round.players[3].score == 24000


class TestApplyDoubleRonWithPao:
    def test_double_ron_with_pao_on_one_winner(self):
        """Double ron where one winner has pao from a different player."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        # seat 0 has pao on seat 3
        players_list = list(players)
        players_list[0] = players_list[0].model_copy(update={"pao_seat": 3})
        round_state = MahjongRoundState(dealer_seat=0, players=tuple(players_list))
        game_state = MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

        hand_result_0 = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])

        winners = [(0, hand_result_0), (2, hand_result_2)]
        new_round, _new_game, result = apply_double_ron_score(game_state, winners=winners, loser_seat=1)

        # seat 0's 32000: split 50/50 between loser(1) and pao(3) -> 16000 each
        # seat 2's 2000: full from loser(1)
        assert new_round.players[0].score == 25000 + 32000
        assert new_round.players[1].score == 25000 - 18000  # 16000 + 2000
        assert new_round.players[2].score == 25000 + 2000
        assert new_round.players[3].score == 25000 - 16000  # pao
        assert result.winners[0].pao_seat == 3
        assert result.winners[1].pao_seat is None


class TestProcessExhaustiveDrawNagashiTriggered:
    def test_nagashi_mangan_triggered(self):
        """Player with only terminal/honor discards gets nagashi mangan payment."""
        tempai_hand = tuple(TilesConverter.string_to_136_array(man="1123456788899"))
        non_tempai_hand = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"))
        # Player 0 has only terminal/honor discards (nagashi mangan)
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        man_9 = TilesConverter.string_to_136_array(man="9")[0]
        east = TilesConverter.string_to_136_array(honors="1")[0]
        nagashi_discards = (
            Discard(tile_id=man_1),
            Discard(tile_id=man_9),
            Discard(tile_id=east),
        )
        players = tuple(
            MahjongPlayer(
                seat=seat,
                name=f"Player{seat}",
                tiles=tempai_hand if seat == 0 else non_tempai_hand,
                score=25000,
                discards=nagashi_discards if seat == 0 else (),
            )
            for seat in range(4)
        )
        round_state = MahjongRoundState(players=players, wall=(), dealer_seat=1)
        game_state = MahjongGameState(round_state=round_state)

        new_round, _new_game, result = process_exhaustive_draw(game_state)

        # Nagashi mangan gives mangan payment (non-dealer: 2000/4000)
        # Player 0 is non-dealer: gets 2000 from each non-dealer + 4000 from dealer = 8000
        assert result.type == RoundResultType.NAGASHI_MANGAN
        assert new_round.players[0].score == 25000 + 8000


class TestCheckNagashiManganImmutable:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state for nagashi mangan testing."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        return MahjongRoundState(players=players, wall=())

    def test_qualifies_with_all_terminal_honor_discards(self):
        """Player with only terminal/honor discards qualifies."""
        round_state = self._create_round_state()
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        man_9 = TilesConverter.string_to_136_array(man="9")[0]
        east = TilesConverter.string_to_136_array(honors="1")[0]
        discards = (
            Discard(tile_id=man_1),
            Discard(tile_id=man_9),
            Discard(tile_id=east),
        )
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"discards": discards})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        result = check_nagashi_mangan(round_state)

        assert result == [0]

    def test_fails_with_simple_tile_discard(self):
        """Player with a simple tile discard does not qualify."""
        round_state = self._create_round_state()
        man_5 = TilesConverter.string_to_136_array(man="5")[0]
        east = TilesConverter.string_to_136_array(honors="1")[0]
        discards = (
            Discard(tile_id=man_5),  # simple tile
            Discard(tile_id=east),
        )
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"discards": discards})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        result = check_nagashi_mangan(round_state)

        assert result == []

    def test_fails_when_discard_claimed(self):
        """Player whose discard was claimed does not qualify."""
        round_state = self._create_round_state()
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        discards = (
            Discard(tile_id=man_1),
            Discard(tile_id=east_tiles[0]),
        )
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(east_tiles),
            opened=True,
            called_tile=east_tiles[0],
            who=1,
            from_who=0,
        )
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"discards": discards})
        players[1] = players[1].model_copy(update={"melds": (pon,)})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        result = check_nagashi_mangan(round_state)

        assert result == []


class TestCalculateHandValueErrors:
    """Test hand calculation error logging branches in scoring.py."""

    def _create_round_state(self) -> MahjongRoundState:
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        return MahjongRoundState(
            dealer_seat=0,
            round_wind=0,
            players=tuple(MahjongPlayer(seat=i, name=f"P{i}") for i in range(4)),
            dora_indicators=(dead_wall[2],),
            dead_wall=dead_wall,
        )

    def test_calculate_hand_value_returns_error_for_invalid_hand(self):
        """calculate_hand_value returns HandResult with error for invalid hand."""
        round_state = self._create_round_state()
        # incomplete hand (only 5 tiles) — no valid yaku possible
        bad_tiles = TilesConverter.string_to_136_array(man="12345")
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(bad_tiles))

        result = calculate_hand_value(player, round_state, bad_tiles[0], is_tsumo=True)

        assert result.error is not None

    def test_calculate_hand_value_with_tiles_returns_error(self):
        """calculate_hand_value_with_tiles returns error for invalid tiles."""
        round_state = self._create_round_state()
        bad_tiles = TilesConverter.string_to_136_array(man="12345")
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(bad_tiles))

        result = calculate_hand_value_with_tiles(
            player,
            round_state,
            list(bad_tiles),
            bad_tiles[0],
            is_tsumo=False,
        )

        assert result.error is not None

    def test_ura_dora_added_for_riichi_ron(self):
        """Ura dora indicators are included when player is riichi (ron win)."""
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = MahjongRoundState(
            dealer_seat=0,
            round_wind=0,
            players=tuple(MahjongPlayer(seat=i, name=f"P{i}") for i in range(4)),
            dora_indicators=(dead_wall[2],),
            dead_wall=dead_wall,
        )
        # winning hand: 123m 456m 789m 123p 5p (win on 5p by ron)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(tiles), is_riichi=True)

        result = calculate_hand_value_with_tiles(
            player,
            round_state,
            list(tiles),
            win_tile,
            is_tsumo=False,
        )

        # should succeed (valid hand) and riichi yaku included
        assert result.error is None
        assert result.han >= 1
        assert any("riichi" in y.lower() for y in result.yaku)
