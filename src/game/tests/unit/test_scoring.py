"""
Unit tests for scoring calculation.
"""

from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.scoring import (
    HandResult,
    apply_double_ron_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
)
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState, seat_to_wind


class TestSeatToWind:
    def test_dealer_is_east(self):
        # dealer at seat 0, player at seat 0 -> East (0)
        assert seat_to_wind(0, 0) == 0

    def test_dealer_plus_one_is_south(self):
        # dealer at seat 0, player at seat 1 -> South (1)
        assert seat_to_wind(1, 0) == 1

    def test_dealer_plus_two_is_west(self):
        # dealer at seat 0, player at seat 2 -> West (2)
        assert seat_to_wind(2, 0) == 2

    def test_dealer_plus_three_is_north(self):
        # dealer at seat 0, player at seat 3 -> North (3)
        assert seat_to_wind(3, 0) == 3

    def test_dealer_at_seat_2(self):
        # dealer at seat 2
        # seat 2 = East, seat 3 = South, seat 0 = West, seat 1 = North
        assert seat_to_wind(2, 2) == 0  # East
        assert seat_to_wind(3, 2) == 1  # South
        assert seat_to_wind(0, 2) == 2  # West
        assert seat_to_wind(1, 2) == 3  # North


class TestCalculateHandValue:
    def _create_game_state(self, dealer_seat: int = 0) -> MahjongGameState:
        """
        Create a game state with 4 players for testing.

        Sets up a mid-game state (some discards) to avoid triggering Tenhou.
        """
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,  # east
            dora_indicators=[0],  # 1m as dora indicator (makes 2m dora)
            wall=list(range(70)),  # some tiles in wall (not empty)
            dead_wall=list(range(14)),  # dummy dead wall for ura dora
            players=players,
            all_discards=[1, 2, 3, 4],  # some discards to avoid tenhou/chiihou
        )
        return MahjongGameState(round_state=round_state)

    def test_menzen_tsumo_hand(self):
        # 123m 456m 789m 123p 55p - pinfu tsumo
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state()
        player = game_state.round_state.players[0]
        player.tiles = tiles

        win_tile = tiles[-1]  # 5p
        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert result.han >= 1  # at least menzen tsumo
        assert result.fu > 0
        assert result.cost_main > 0
        assert len(result.yaku) > 0

    def test_riichi_hand(self):
        # closed hand with riichi
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state()
        player = game_state.round_state.players[0]
        player.tiles = tiles
        player.is_riichi = True

        win_tile = tiles[-1]
        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert result.han >= 2  # riichi + menzen tsumo
        assert "Riichi" in result.yaku

    def test_ippatsu_hand(self):
        # riichi with ippatsu
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state()
        player = game_state.round_state.players[0]
        player.tiles = tiles
        player.is_riichi = True
        player.is_ippatsu = True

        win_tile = tiles[-1]
        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert result.han >= 3  # riichi + ippatsu + menzen tsumo
        assert "Ippatsu" in result.yaku

    def test_ron_hand(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state()
        player = game_state.round_state.players[0]
        player.tiles = tiles
        player.is_riichi = True

        win_tile = tiles[-1]
        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert result.han >= 1  # riichi
        assert "Menzen Tsumo" not in result.yaku  # not a tsumo

    def test_haitei_tsumo(self):
        # last tile draw (haitei)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state()
        game_state.round_state.wall = []  # empty wall = last tile
        player = game_state.round_state.players[0]
        player.tiles = tiles

        win_tile = tiles[-1]
        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert "Haitei Raoyue" in result.yaku

    def test_houtei_ron(self):
        # last discard ron (houtei)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state()
        game_state.round_state.wall = []  # empty wall = last discard possible
        player = game_state.round_state.players[0]
        player.tiles = tiles
        player.is_riichi = True

        win_tile = tiles[-1]
        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert "Houtei Raoyui" in result.yaku

    def test_no_yaku_error(self):
        # open hand with no yaku
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        win_tile = TilesConverter.string_to_136_array(man="5")[:1]
        all_tiles = closed_tiles + pon_tiles + win_tile

        pon = Meld(
            meld_type=Meld.PON, tiles=pon_tiles, opened=True, called_tile=pon_tiles[0], who=0, from_who=1
        )

        game_state = self._create_game_state()
        player = game_state.round_state.players[0]
        player.tiles = all_tiles
        player.melds = [pon]

        result = calculate_hand_value(player, game_state.round_state, win_tile[0], is_tsumo=True)

        assert result.error == "no_yaku"


class TestApplyTsumoScore:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = [MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
        )
        return MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_non_dealer_tsumo_basic(self):
        # non-dealer wins with 30fu 1han = 1000/500
        game_state = self._create_game_state()
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=["Riichi"])

        result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # winner (seat 1) gets 2000 total (1000 from dealer + 500*2 from non-dealers)
        assert game_state.round_state.players[1].score == 25000 + 2000
        # dealer (seat 0) pays 1000
        assert game_state.round_state.players[0].score == 25000 - 1000
        # other non-dealers pay 500 each
        assert game_state.round_state.players[2].score == 25000 - 500
        assert game_state.round_state.players[3].score == 25000 - 500
        assert result.type == "tsumo"
        assert result.winner_seat == 1

    def test_dealer_tsumo_basic(self):
        # dealer wins with 30fu 2han = 2000 all (dealer tsumo)
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Tsumo"])

        apply_tsumo_score(game_state, winner_seat=0, hand_result=hand_result)

        # dealer (seat 0) gets 6000 total (2000 * 3)
        assert game_state.round_state.players[0].score == 25000 + 6000
        # each non-dealer pays 2000
        assert game_state.round_state.players[1].score == 25000 - 2000
        assert game_state.round_state.players[2].score == 25000 - 2000
        assert game_state.round_state.players[3].score == 25000 - 2000

    def test_tsumo_with_honba(self):
        # tsumo with 2 honba sticks = +200 total (100 per loser)
        game_state = self._create_game_state()
        game_state.honba_sticks = 2
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=["Riichi"])

        apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # winner gets 2000 + 600 (300 * 2 honba, but per-loser so 100*2*3=600)
        assert game_state.round_state.players[1].score == 25000 + 2600
        # dealer pays 1000 + 200
        assert game_state.round_state.players[0].score == 25000 - 1200
        # non-dealers pay 500 + 200
        assert game_state.round_state.players[2].score == 25000 - 700
        assert game_state.round_state.players[3].score == 25000 - 700

    def test_tsumo_with_riichi_sticks(self):
        # tsumo with 2 riichi sticks on table
        game_state = self._create_game_state()
        game_state.riichi_sticks = 2
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=["Riichi"])

        result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # winner gets 2000 + 2000 (riichi sticks)
        assert game_state.round_state.players[1].score == 25000 + 4000
        # riichi sticks should be cleared
        assert game_state.riichi_sticks == 0
        assert result.riichi_sticks_collected == 2


class TestApplyRonScore:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = [MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
        )
        return MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_ron_basic(self):
        # basic ron with 30fu 2han = 2000
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Pinfu"])

        result = apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        # winner gets 2000
        assert game_state.round_state.players[0].score == 25000 + 2000
        # loser pays 2000
        assert game_state.round_state.players[1].score == 25000 - 2000
        # others unaffected
        assert game_state.round_state.players[2].score == 25000
        assert game_state.round_state.players[3].score == 25000
        assert result.type == "ron"

    def test_ron_with_honba(self):
        # ron with 3 honba sticks = +900 total
        game_state = self._create_game_state()
        game_state.honba_sticks = 3
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Pinfu"])

        apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        # winner gets 2000 + 900
        assert game_state.round_state.players[0].score == 25000 + 2900
        # loser pays 2000 + 900
        assert game_state.round_state.players[1].score == 25000 - 2900

    def test_ron_with_riichi_sticks(self):
        # ron with 3 riichi sticks
        game_state = self._create_game_state()
        game_state.riichi_sticks = 3
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Pinfu"])

        result = apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        # winner gets 2000 + 3000
        assert game_state.round_state.players[0].score == 25000 + 5000
        # loser only pays 2000
        assert game_state.round_state.players[1].score == 25000 - 2000
        # riichi sticks cleared
        assert game_state.riichi_sticks == 0
        assert result.riichi_sticks_collected == 3


class TestApplyDoubleRonScore:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = [MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
        )
        return MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_double_ron_basic(self):
        # two winners ron off one discard
        game_state = self._create_game_state()
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=["Riichi", "Tanyao"])

        winners = [(0, hand_result_1), (2, hand_result_2)]
        result = apply_double_ron_score(game_state, winners=winners, loser_seat=1)

        # seat 0 wins 2000
        assert game_state.round_state.players[0].score == 25000 + 2000
        # seat 2 wins 4000
        assert game_state.round_state.players[2].score == 25000 + 4000
        # seat 1 pays 6000 total
        assert game_state.round_state.players[1].score == 25000 - 6000
        # seat 3 unaffected
        assert game_state.round_state.players[3].score == 25000
        assert result.type == "double_ron"

    def test_double_ron_with_honba(self):
        # both winners get honba bonus
        game_state = self._create_game_state()
        game_state.honba_sticks = 2
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Tanyao"])

        winners = [(0, hand_result_1), (2, hand_result_2)]
        apply_double_ron_score(game_state, winners=winners, loser_seat=1)

        # each winner gets 2000 + 600 honba
        assert game_state.round_state.players[0].score == 25000 + 2600
        assert game_state.round_state.players[2].score == 25000 + 2600
        # loser pays both (2000+600)*2 = 5200
        assert game_state.round_state.players[1].score == 25000 - 5200

    def test_double_ron_riichi_sticks_to_closest(self):
        # riichi sticks go to winner closest to loser's right (counter-clockwise)
        # loser is seat 1, checking seats 2, 3, 0 in order
        # if winners are 0 and 2, seat 2 is checked first
        game_state = self._create_game_state()
        game_state.riichi_sticks = 2
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Tanyao"])

        winners = [(0, hand_result_1), (2, hand_result_2)]
        result = apply_double_ron_score(game_state, winners=winners, loser_seat=1)

        # seat 2 is closer (loser_seat + 1 = seat 2)
        # seat 2 gets 2000 + 2000 riichi
        assert game_state.round_state.players[2].score == 25000 + 4000
        # seat 0 only gets 2000
        assert game_state.round_state.players[0].score == 25000 + 2000
        # riichi sticks cleared
        assert game_state.riichi_sticks == 0

        # verify which winner got riichi sticks
        for w in result.winners:
            if w.winner_seat == 2:
                assert w.riichi_sticks_collected == 2
            else:
                assert w.riichi_sticks_collected == 0

    def test_double_ron_riichi_sticks_other_order(self):
        # different loser seat changes who gets riichi
        # loser is seat 3, checking seats 0, 1, 2 in order
        # if winners are 0 and 2, seat 0 is checked first
        game_state = self._create_game_state()
        game_state.riichi_sticks = 1
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Tanyao"])

        winners = [(0, hand_result_1), (2, hand_result_2)]
        apply_double_ron_score(game_state, winners=winners, loser_seat=3)

        # seat 0 is closer (loser_seat + 1 = seat 0)
        # seat 0 gets 2000 + 1000 riichi
        assert game_state.round_state.players[0].score == 25000 + 3000
        # seat 2 only gets 2000
        assert game_state.round_state.players[2].score == 25000 + 2000
