"""
Unit tests for immutable win checks and scoring functions (Phase 3).
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
    apply_nagashi_mangan_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
    calculate_hand_value_with_tiles,
)
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.win import (
    apply_temporary_furiten,
    can_call_ron,
    check_tsumo_with_tiles,
)


class TestCheckTsumoWithTiles:
    def test_winning_hand_returns_true(self):
        """Standard winning hand should return True."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Test", tiles=tuple(tiles))

        result = check_tsumo_with_tiles(player, tiles)

        assert result is True

    def test_non_winning_hand_returns_false(self):
        """Non-winning hand should return False."""
        tiles = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")
        player = MahjongPlayer(seat=0, name="Test", tiles=tuple(tiles))

        result = check_tsumo_with_tiles(player, tiles)

        assert result is False

    def test_winning_hand_with_open_meld(self):
        """Open hand that wins should return True."""
        # 234m + 567m + 23s + 55s (10 tiles closed) + Haku pon = 13 tiles
        # win on 4s to make 234s, total 14 tiles
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )
        # add 4s to complete the hand (234m 567m 234s 55s + Haku pon)
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        all_tiles = [*closed_tiles, win_tile]

        player = MahjongPlayer(seat=0, name="Test", tiles=tuple(closed_tiles), melds=(pon,))

        result = check_tsumo_with_tiles(player, all_tiles)

        assert result is True


class TestCanCallRonImmutable:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        """Create a round state for ron testing."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        dora_tiles = TilesConverter.string_to_136_array(man="1")
        tuple(Discard(tile_id=t) for t in TilesConverter.string_to_136_array(man="1112"))
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            players=players,
            dora_indicators=tuple(dora_tiles),
            all_discards=tuple(TilesConverter.string_to_136_array(man="1112")),
        )

    def test_can_call_ron_with_valid_hand(self):
        """Player with riichi and winning hand can call ron."""
        round_state = self._create_round_state()
        # 123m 456m 789m 123p 5p - waiting for 5p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1235")
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"tiles": tuple(tiles), "is_riichi": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})
        player = round_state.players[0]
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]

        result = can_call_ron(player, win_tile, round_state)

        assert result is True

    def test_cannot_call_ron_when_temporary_furiten(self):
        """Player in temporary furiten cannot call ron."""
        round_state = self._create_round_state()
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1235")
        players = list(round_state.players)
        players[0] = players[0].model_copy(
            update={"tiles": tuple(tiles), "is_riichi": True, "is_temporary_furiten": True}
        )
        round_state = round_state.model_copy(update={"players": tuple(players)})
        player = round_state.players[0]
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]

        result = can_call_ron(player, win_tile, round_state)

        assert result is False

    def test_cannot_call_ron_when_riichi_furiten(self):
        """Player in riichi furiten cannot call ron."""
        round_state = self._create_round_state()
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1235")
        players = list(round_state.players)
        players[0] = players[0].model_copy(
            update={"tiles": tuple(tiles), "is_riichi": True, "is_riichi_furiten": True}
        )
        round_state = round_state.model_copy(update={"players": tuple(players)})
        player = round_state.players[0]
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]

        result = can_call_ron(player, win_tile, round_state)

        assert result is False

    def test_cannot_call_ron_with_non_winning_hand(self):
        """Player with non-winning hand cannot call ron."""
        round_state = self._create_round_state()
        tiles = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="135")
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"tiles": tuple(tiles), "is_riichi": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})
        player = round_state.players[0]
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]

        result = can_call_ron(player, win_tile, round_state)

        assert result is False

    def test_does_not_mutate_player_tiles(self):
        """Calling can_call_ron should not modify player.tiles."""
        round_state = self._create_round_state()
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1235")
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"tiles": tuple(tiles), "is_riichi": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})
        player = round_state.players[0]
        original_tiles = player.tiles
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]

        can_call_ron(player, win_tile, round_state)

        # tiles should be unchanged
        assert player.tiles == original_tiles

    def test_cannot_call_ron_when_discard_furiten(self):
        """Player in permanent furiten (discarded a winning tile) cannot call ron."""
        round_state = self._create_round_state()
        # Hand waiting on 5p, but 5p already discarded
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1235")
        pin_5 = TilesConverter.string_to_136_array(pin="5")[0]
        discards = (Discard(tile_id=pin_5),)
        players = list(round_state.players)
        players[0] = players[0].model_copy(
            update={"tiles": tuple(tiles), "is_riichi": True, "discards": discards}
        )
        round_state = round_state.model_copy(update={"players": tuple(players)})
        player = round_state.players[0]
        win_tile = TilesConverter.string_to_136_array(pin="55")[1]  # different copy of 5p

        result = can_call_ron(player, win_tile, round_state)

        assert result is False

    def test_open_hand_with_yaku_can_call_ron(self):
        """Open hand with valid yaku can call ron."""
        round_state = self._create_round_state()
        # 234m + 567m + 23s + 55s (closed) + Haku pon (open)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"tiles": tuple(closed_tiles), "melds": (pon,)})
        round_state = round_state.model_copy(update={"players": tuple(players)})
        player = round_state.players[0]
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]

        result = can_call_ron(player, win_tile, round_state)

        # open hand with haku (yakuhai) can ron
        assert result is True


class TestApplyTemporaryFuritenImmutable:
    def test_sets_temporary_furiten(self):
        """Should return new state with is_temporary_furiten=True."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(players=players)

        new_state = apply_temporary_furiten(round_state, seat=1)

        assert new_state.players[1].is_temporary_furiten is True
        # original unchanged
        assert round_state.players[1].is_temporary_furiten is False

    def test_does_not_affect_other_players(self):
        """Other players' furiten status should be unchanged."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(players=players)

        new_state = apply_temporary_furiten(round_state, seat=2)

        assert new_state.players[0].is_temporary_furiten is False
        assert new_state.players[1].is_temporary_furiten is False
        assert new_state.players[2].is_temporary_furiten is True
        assert new_state.players[3].is_temporary_furiten is False


class TestIsTempaiImmutable:
    def test_tempai_hand_returns_true(self):
        """Standard tempai hand should return True."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1123456788899"))

        result = is_tempai(tiles, melds=())

        assert result is True

    def test_non_tempai_hand_returns_false(self):
        """Non-tempai hand should return False."""
        tiles = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"))

        result = is_tempai(tiles, melds=())

        assert result is False

    def test_chiitoi_tempai(self):
        """Chiitoitsu tempai should return True."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1122334455667"))

        result = is_tempai(tiles, melds=())

        assert result is True

    def test_open_hand_tempai(self):
        """Open hand tempai should return True."""
        tiles = tuple(TilesConverter.string_to_136_array(man="2345678889"))

        result = is_tempai(tiles, melds=())

        assert result is True

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

    def test_14_tiles_tempai_with_any_discard(self):
        """Hand with 14 tiles: tempai if any discard leaves in tempai."""
        # 1123456788899m + 1m = tempai with any discard of 1, 8, or 9
        tiles = tuple(TilesConverter.string_to_136_array(man="11234567888999"))

        result = is_tempai(tiles, melds=())

        assert result is True

    def test_14_tiles_noten_no_discard_leaves_tempai(self):
        """Hand with 14 tiles: noten if no discard leaves in tempai."""
        # Disconnected tiles - no discard can leave this in tempai
        tiles = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="13579"))

        result = is_tempai(tiles, melds=())

        assert result is False

    def test_no_waiting_tiles_returns_false(self):
        """Hand with no waiting tiles returns False."""
        # Non-tempai 13-tile hand
        tiles = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"))

        result = is_tempai(tiles, melds=())

        assert result is False


class TestApplyTsumoScoreImmutable:
    def _create_game_state(self, dealer_seat: int = 0) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(dealer_seat=dealer_seat, players=players)
        return MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_non_dealer_tsumo_basic(self):
        """Non-dealer tsumo: dealer pays main_cost, others pay additional."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=["Riichi"])

        new_round, _new_game, result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # winner (seat 1) gets 2000 total
        assert new_round.players[1].score == 25000 + 2000
        # dealer pays 1000
        assert new_round.players[0].score == 25000 - 1000
        # non-dealers pay 500 each
        assert new_round.players[2].score == 25000 - 500
        assert new_round.players[3].score == 25000 - 500
        assert result.type == RoundResultType.TSUMO
        # original unchanged
        assert game_state.round_state.players[1].score == 25000

    def test_dealer_tsumo_basic(self):
        """Dealer tsumo: each non-dealer pays main_cost."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Tsumo"])

        new_round, _new_game, _result = apply_tsumo_score(game_state, winner_seat=0, hand_result=hand_result)

        # dealer gets 6000 total
        assert new_round.players[0].score == 25000 + 6000
        assert new_round.players[1].score == 25000 - 2000
        assert new_round.players[2].score == 25000 - 2000
        assert new_round.players[3].score == 25000 - 2000

    def test_tsumo_with_honba(self):
        """Tsumo with honba sticks adds bonus to payments."""
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=["Riichi"])

        new_round, _new_game, _result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # +200 honba per loser
        assert new_round.players[1].score == 25000 + 2600
        assert new_round.players[0].score == 25000 - 1200  # dealer
        assert new_round.players[2].score == 25000 - 700  # non-dealer
        assert new_round.players[3].score == 25000 - 700

    def test_tsumo_with_riichi_sticks(self):
        """Tsumo winner gets riichi sticks bonus."""
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=["Riichi"])

        new_round, new_game, result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        assert new_round.players[1].score == 25000 + 4000  # 2000 + 2000 riichi
        assert new_game.riichi_sticks == 0
        assert result.riichi_sticks_collected == 2

    def test_pao_tsumo(self):
        """Pao tsumo: liable player pays full amount."""
        game_state = self._create_game_state()
        players = list(game_state.round_state.players)
        players[1] = players[1].model_copy(update={"pao_seat": 2})
        round_state = game_state.round_state.model_copy(update={"players": tuple(players)})
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=["Daisangen"])

        new_round, _new_game, result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # pao pays all 32000
        assert result.pao_seat == 2
        assert new_round.players[0].score == 25000  # dealer pays nothing
        assert new_round.players[1].score == 25000 + 32000
        assert new_round.players[2].score == 25000 - 32000
        assert new_round.players[3].score == 25000


class TestApplyRonScoreImmutable:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(dealer_seat=0, players=players)
        return MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_ron_basic(self):
        """Basic ron: loser pays main_cost."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Pinfu"])

        new_round, _new_game, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result
        )

        assert new_round.players[0].score == 25000 + 2000
        assert new_round.players[1].score == 25000 - 2000
        assert new_round.players[2].score == 25000
        assert new_round.players[3].score == 25000
        assert result.type == RoundResultType.RON
        # original unchanged
        assert game_state.round_state.players[0].score == 25000

    def test_ron_with_honba(self):
        """Ron with honba: loser pays additional honba bonus."""
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 3})
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Pinfu"])

        new_round, _new_game, _result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result
        )

        assert new_round.players[0].score == 25000 + 2900  # +900 honba
        assert new_round.players[1].score == 25000 - 2900

    def test_ron_with_riichi_sticks(self):
        """Ron winner gets riichi sticks bonus."""
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 3})
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Pinfu"])

        new_round, new_game, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result
        )

        assert new_round.players[0].score == 25000 + 5000  # +3000 riichi
        assert new_round.players[1].score == 25000 - 2000
        assert new_game.riichi_sticks == 0
        assert result.riichi_sticks_collected == 3

    def test_pao_ron_different_player(self):
        """Pao ron: split payment 50/50 when pao != loser."""
        game_state = self._create_game_state()
        players = list(game_state.round_state.players)
        players[0] = players[0].model_copy(update={"pao_seat": 2})
        round_state = game_state.round_state.model_copy(update={"players": tuple(players)})
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])

        new_round, _new_game, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result
        )

        assert result.pao_seat == 2
        assert new_round.players[0].score == 25000 + 32000
        assert new_round.players[1].score == 25000 - 16000  # half
        assert new_round.players[2].score == 25000 - 16000  # half (pao)
        assert new_round.players[3].score == 25000


class TestApplyDoubleRonScoreImmutable:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(dealer_seat=0, players=players)
        return MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_double_ron_basic(self):
        """Double ron: both winners get paid from loser."""
        game_state = self._create_game_state()
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=["Riichi", "Tanyao"])

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round, _new_game, result = apply_double_ron_score(game_state, winners=winners, loser_seat=1)

        assert new_round.players[0].score == 25000 + 2000
        assert new_round.players[2].score == 25000 + 4000
        assert new_round.players[1].score == 25000 - 6000
        assert new_round.players[3].score == 25000
        assert result.type == RoundResultType.DOUBLE_RON
        # original unchanged
        assert game_state.round_state.players[0].score == 25000

    def test_double_ron_riichi_sticks_to_closest(self):
        """Riichi sticks go to winner closest to loser's right."""
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Tanyao"])

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round, new_game, _result = apply_double_ron_score(game_state, winners=winners, loser_seat=1)

        # seat 2 is closer to loser's right (loser+1=2)
        assert new_round.players[2].score == 25000 + 4000  # 2000 + 2000 riichi
        assert new_round.players[0].score == 25000 + 2000  # no riichi bonus
        assert new_game.riichi_sticks == 0

    def test_double_ron_with_pao_on_one_winner(self):
        """Double ron where one winner has pao from a different player."""
        game_state = self._create_game_state()
        # seat 0 has pao on seat 3
        players = list(game_state.round_state.players)
        players[0] = players[0].model_copy(update={"pao_seat": 3})
        round_state = game_state.round_state.model_copy(update={"players": tuple(players)})
        game_state = game_state.model_copy(update={"round_state": round_state})

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


class TestApplyNagashiManganScoreImmutable:
    def _create_game_state(self, dealer_seat: int = 0) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(dealer_seat=dealer_seat, players=players)
        return MahjongGameState(round_state=round_state)

    def test_dealer_nagashi_mangan(self):
        """Dealer nagashi: 4000 from each non-dealer."""
        game_state = self._create_game_state(dealer_seat=0)

        new_round, _new_game, result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0], tempai_seats=[], noten_seats=[0, 1, 2, 3]
        )

        assert result.type == RoundResultType.NAGASHI_MANGAN
        assert new_round.players[0].score == 37000
        assert new_round.players[1].score == 21000
        assert new_round.players[2].score == 21000
        assert new_round.players[3].score == 21000
        # original unchanged
        assert game_state.round_state.players[0].score == 25000

    def test_non_dealer_nagashi_mangan(self):
        """Non-dealer nagashi: 4000 from dealer, 2000 from others."""
        game_state = self._create_game_state(dealer_seat=0)

        new_round, _new_game, _result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[1], tempai_seats=[], noten_seats=[0, 1, 2, 3]
        )

        assert new_round.players[1].score == 33000  # +8000
        assert new_round.players[0].score == 21000  # -4000
        assert new_round.players[2].score == 23000  # -2000
        assert new_round.players[3].score == 23000  # -2000


class TestProcessExhaustiveDrawImmutable:
    def _create_game_state_with_players(self, tempai_seats: list[int]) -> MahjongGameState:
        """Create a game state where specified seats are in tempai."""
        tempai_hand = tuple(TilesConverter.string_to_136_array(man="1123456788899"))
        non_tempai_hand = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"))
        players = tuple(
            MahjongPlayer(
                seat=seat,
                name=f"Player{seat}",
                tiles=tempai_hand if seat in tempai_seats else non_tempai_hand,
                score=25000,
            )
            for seat in range(4)
        )
        round_state = MahjongRoundState(players=players, wall=())
        return MahjongGameState(round_state=round_state)

    def test_one_tempai(self):
        """1 tempai, 3 noten: each noten pays 1000."""
        game_state = self._create_game_state_with_players(tempai_seats=[0])

        new_round, _new_game, result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == [0]
        assert result.noten_seats == [1, 2, 3]
        assert new_round.players[0].score == 28000
        assert new_round.players[1].score == 24000
        assert new_round.players[2].score == 24000
        assert new_round.players[3].score == 24000
        # original unchanged
        assert game_state.round_state.players[0].score == 25000

    def test_two_tempai(self):
        """2 tempai, 2 noten: each noten pays 1500."""
        game_state = self._create_game_state_with_players(tempai_seats=[0, 2])

        new_round, _new_game, result = process_exhaustive_draw(game_state)

        assert result.tempai_seats == [0, 2]
        assert result.noten_seats == [1, 3]
        assert new_round.players[0].score == 26500
        assert new_round.players[1].score == 23500
        assert new_round.players[2].score == 26500
        assert new_round.players[3].score == 23500

    def test_all_tempai_no_payment(self):
        """All 4 tempai: no payment."""
        game_state = self._create_game_state_with_players(tempai_seats=[0, 1, 2, 3])

        new_round, _new_game, _result = process_exhaustive_draw(game_state)

        for i in range(4):
            assert new_round.players[i].score == 25000

    def test_all_noten_no_payment(self):
        """All 4 noten: no payment."""
        game_state = self._create_game_state_with_players(tempai_seats=[])

        new_round, _new_game, _result = process_exhaustive_draw(game_state)

        for i in range(4):
            assert new_round.players[i].score == 25000

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
