"""
Unit tests for scoring calculation.
"""

from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.scoring import (
    HandResult,
    apply_double_ron_score,
    apply_nagashi_mangan_score,
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
        dora_indicator_tiles = TilesConverter.string_to_136_array(man="1")
        dummy_discard_tiles = TilesConverter.string_to_136_array(man="1112")
        round_state = MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,  # east
            dora_indicators=dora_indicator_tiles,  # 1m as dora indicator (makes 2m dora)
            wall=list(range(70)),  # some tiles in wall (not empty)
            dead_wall=list(range(14)),  # dummy dead wall for ura dora
            players=players,
            all_discards=dummy_discard_tiles,  # some discards to avoid tenhou/chiihou
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

    def test_ron_open_hand_meld_tiles_removed_from_hand(self):
        # after meld call in actual gameplay, meld tiles are removed from player.tiles
        # closed: 234m 567m 23s 55s (10 tiles) + PON(Haku) (meld) = 13 total
        # ron on 4s to complete: 234m 567m 234s 55s + PON(Haku) = 14 total
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = Meld(
            meld_type=Meld.PON, tiles=haku_tiles, opened=True, called_tile=haku_tiles[0], who=0, from_who=1
        )

        game_state = self._create_game_state()
        player = game_state.round_state.players[0]
        # only closed tiles in hand (matching actual gameplay after meld call)
        player.tiles = closed_tiles
        player.melds = [pon]

        # add ron tile
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        player.tiles.append(win_tile)

        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert result.han >= 1  # yakuhai (haku)
        assert result.cost_main > 0

    def test_tsumo_open_hand_meld_tiles_removed_from_hand(self):
        # after meld call in actual gameplay, meld tiles are removed from player.tiles
        # closed: 234m 567m 234s 55s (11 tiles) + PON(Haku) (meld) = 14 total (drawn 4s)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = Meld(
            meld_type=Meld.PON, tiles=haku_tiles, opened=True, called_tile=haku_tiles[0], who=0, from_who=1
        )

        game_state = self._create_game_state()
        player = game_state.round_state.players[0]
        # only closed tiles in hand (matching actual gameplay after meld call)
        player.tiles = closed_tiles
        player.melds = [pon]

        win_tile = player.tiles[-1]  # last tile drawn (5s)
        result = calculate_hand_value(player, game_state.round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert result.han >= 1  # yakuhai (haku)
        assert result.cost_main > 0


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


class TestApplyNagashiManganScore:
    def _create_game_state(self, dealer_seat: int = 0) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        # use non-tempai hands (disconnected tiles) by default
        players = [
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                score=25000,
                tiles=TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"),
            )
            for i in range(4)
        ]
        round_state = MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
            players=players,
        )
        return MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_dealer_nagashi_mangan(self):
        """Dealer nagashi mangan: 4000 from each non-dealer."""
        game_state = self._create_game_state(dealer_seat=0)

        result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0], tempai_seats=[], noten_seats=[0, 1, 2, 3]
        )

        assert result.type == "nagashi_mangan"
        assert result.qualifying_seats == [0]
        assert result.score_changes[0] == 12000
        assert result.score_changes[1] == -4000
        assert result.score_changes[2] == -4000
        assert result.score_changes[3] == -4000
        assert game_state.round_state.players[0].score == 37000
        assert game_state.round_state.players[1].score == 21000
        assert game_state.round_state.players[2].score == 21000
        assert game_state.round_state.players[3].score == 21000

    def test_non_dealer_nagashi_mangan(self):
        """Non-dealer nagashi mangan: 4000 from dealer + 2000 from each non-dealer."""
        game_state = self._create_game_state(dealer_seat=0)

        result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[1], tempai_seats=[], noten_seats=[0, 1, 2, 3]
        )

        assert result.score_changes[1] == 8000
        assert result.score_changes[0] == -4000  # dealer pays 4000
        assert result.score_changes[2] == -2000  # non-dealer pays 2000
        assert result.score_changes[3] == -2000  # non-dealer pays 2000
        assert game_state.round_state.players[1].score == 33000
        assert game_state.round_state.players[0].score == 21000
        assert game_state.round_state.players[2].score == 23000
        assert game_state.round_state.players[3].score == 23000

    def test_multiple_qualifying_players(self):
        """Multiple players qualifying: each receives independent mangan payment."""
        game_state = self._create_game_state(dealer_seat=0)

        result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0, 2], tempai_seats=[], noten_seats=[0, 1, 2, 3]
        )

        # seat 0 (dealer): +12000 from nagashi, -4000 paying seat 2 (dealer pays 4000)
        # seat 2 (non-dealer): +8000 from nagashi, -4000 paying seat 0 (pays dealer 4000)
        assert result.score_changes[0] == 12000 - 4000  # 8000
        assert result.score_changes[2] == 8000 - 4000  # 4000
        # seat 1: pays 4000 to seat 0 + 2000 to seat 2 = -6000
        assert result.score_changes[1] == -6000
        # seat 3: pays 4000 to seat 0 + 2000 to seat 2 = -6000
        assert result.score_changes[3] == -6000
        # verify total is zero
        assert sum(result.score_changes.values()) == 0

    def test_tempai_and_noten_passed_through(self):
        """Tempai/noten seats are passed through to the result."""
        game_state = self._create_game_state(dealer_seat=0)

        result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0], tempai_seats=[1], noten_seats=[0, 2, 3]
        )

        assert result.tempai_seats == [1]
        assert result.noten_seats == [0, 2, 3]


class TestPaoTsumoScoring:
    """Tests for pao (liability) in tsumo wins."""

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

    def test_pao_tsumo_non_dealer_yakuman(self):
        """Pao tsumo: liable player pays the full amount, others pay nothing."""
        game_state = self._create_game_state()
        # seat 1 wins with pao on seat 2
        # yakuman tsumo: dealer pays 16000, non-dealer pays 8000 each
        game_state.round_state.players[1].pao_seat = 2
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=["Daisangen"])

        result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # total would be: 16000 (from dealer) + 8000 + 8000 = 32000
        # pao player (seat 2) pays all 32000
        assert result.pao_seat == 2
        assert game_state.round_state.players[0].score == 25000  # dealer pays nothing
        assert game_state.round_state.players[1].score == 25000 + 32000  # winner gets all
        assert game_state.round_state.players[2].score == 25000 - 32000  # pao pays all
        assert game_state.round_state.players[3].score == 25000  # other pays nothing

    def test_pao_tsumo_dealer_yakuman(self):
        """Pao tsumo as dealer: liable player pays the full amount."""
        game_state = self._create_game_state()
        # seat 0 (dealer) wins with pao on seat 3
        # dealer yakuman tsumo: each non-dealer pays 16000
        game_state.round_state.players[0].pao_seat = 3
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=0, yaku=["Daisangen"])

        result = apply_tsumo_score(game_state, winner_seat=0, hand_result=hand_result)

        # total would be: 16000 * 3 = 48000
        assert result.pao_seat == 3
        assert game_state.round_state.players[0].score == 25000 + 48000
        assert game_state.round_state.players[1].score == 25000
        assert game_state.round_state.players[2].score == 25000
        assert game_state.round_state.players[3].score == 25000 - 48000

    def test_pao_tsumo_with_riichi_sticks(self):
        """Pao tsumo: riichi sticks still go to winner."""
        game_state = self._create_game_state()
        game_state.riichi_sticks = 2
        game_state.round_state.players[1].pao_seat = 2
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=["Daisangen"])

        result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # total tsumo: 32000 + 2000 riichi bonus
        assert game_state.round_state.players[1].score == 25000 + 34000
        assert game_state.round_state.players[2].score == 25000 - 32000
        assert result.riichi_sticks_collected == 2

    def test_pao_tsumo_with_honba(self):
        """Pao tsumo with honba: liable player pays full honba too."""
        game_state = self._create_game_state()
        game_state.honba_sticks = 2
        game_state.round_state.players[1].pao_seat = 2
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=["Daisangen"])

        apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # honba: 100 per loser * 2 sticks = 200 per loser, 600 total
        # total normal: 32000 + 600 honba = 32600
        assert game_state.round_state.players[1].score == 25000 + 32600
        assert game_state.round_state.players[2].score == 25000 - 32600

    def test_no_pao_tsumo_normal_scoring(self):
        """Without pao, tsumo scoring is normal."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=["Riichi"])

        result = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        assert result.pao_seat is None
        assert game_state.round_state.players[0].score == 25000 - 1000
        assert game_state.round_state.players[1].score == 25000 + 2000
        assert game_state.round_state.players[2].score == 25000 - 500
        assert game_state.round_state.players[3].score == 25000 - 500


class TestPaoRonScoring:
    """Tests for pao (liability) in ron wins."""

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

    def test_pao_ron_different_player(self):
        """Pao ron: when pao player != loser, payment is split 50/50."""
        game_state = self._create_game_state()
        # seat 0 wins by ron off seat 1, pao on seat 2
        game_state.round_state.players[0].pao_seat = 2
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])

        result = apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        # 32000 split: loser pays 16000, pao pays 16000
        assert result.pao_seat == 2
        assert game_state.round_state.players[0].score == 25000 + 32000
        assert game_state.round_state.players[1].score == 25000 - 16000
        assert game_state.round_state.players[2].score == 25000 - 16000
        assert game_state.round_state.players[3].score == 25000

    def test_pao_ron_same_player(self):
        """Pao ron: when pao player == loser, normal ron applies."""
        game_state = self._create_game_state()
        # seat 0 wins by ron off seat 1, pao also on seat 1
        game_state.round_state.players[0].pao_seat = 1
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])

        result = apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        # pao == loser: normal ron, loser pays full
        assert result.pao_seat == 1
        assert game_state.round_state.players[0].score == 25000 + 32000
        assert game_state.round_state.players[1].score == 25000 - 32000
        assert game_state.round_state.players[2].score == 25000
        assert game_state.round_state.players[3].score == 25000

    def test_pao_ron_with_honba(self):
        """Pao ron with honba: honba is included in the split."""
        game_state = self._create_game_state()
        game_state.honba_sticks = 2
        game_state.round_state.players[0].pao_seat = 2
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])

        apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        # total: 32000 + 600 honba = 32600, split: 16300 each
        assert game_state.round_state.players[0].score == 25000 + 32600
        assert game_state.round_state.players[1].score == 25000 - 16300
        assert game_state.round_state.players[2].score == 25000 - 16300

    def test_pao_ron_with_riichi_sticks(self):
        """Pao ron: riichi sticks still go to winner."""
        game_state = self._create_game_state()
        game_state.riichi_sticks = 1
        game_state.round_state.players[0].pao_seat = 2
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])

        result = apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        # 32000 split: loser 16000, pao 16000; winner also gets 1000 riichi
        assert game_state.round_state.players[0].score == 25000 + 33000
        assert game_state.round_state.players[1].score == 25000 - 16000
        assert game_state.round_state.players[2].score == 25000 - 16000
        assert result.riichi_sticks_collected == 1

    def test_no_pao_ron_normal_scoring(self):
        """Without pao, ron scoring is normal."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi", "Pinfu"])

        result = apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        assert result.pao_seat is None
        assert game_state.round_state.players[0].score == 25000 + 2000
        assert game_state.round_state.players[1].score == 25000 - 2000


class TestPaoDoubleRonScoring:
    """Tests for pao (liability) in double ron wins."""

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

    def test_double_ron_one_winner_has_pao(self):
        """Double ron where one winner has pao from a different player."""
        game_state = self._create_game_state()
        # seat 0 has pao on seat 3, seat 2 has no pao
        # both ron off seat 1
        game_state.round_state.players[0].pao_seat = 3
        hand_result_0 = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])

        result = apply_double_ron_score(
            game_state,
            winners=[(0, hand_result_0), (2, hand_result_2)],
            loser_seat=1,
        )

        # seat 0's 32000: split 50/50 between loser(1) and pao(3) -> 16000 each
        # seat 2's 2000: full from loser(1)
        # seat 1 total: -16000 - 2000 = -18000
        # seat 3 total: -16000
        assert game_state.round_state.players[0].score == 25000 + 32000
        assert game_state.round_state.players[1].score == 25000 - 18000
        assert game_state.round_state.players[2].score == 25000 + 2000
        assert game_state.round_state.players[3].score == 25000 - 16000
        assert result.type == "double_ron"
        # pao_seat is propagated to individual winner results
        assert result.winners[0].pao_seat == 3
        assert result.winners[1].pao_seat is None

    def test_double_ron_pao_same_as_loser(self):
        """Double ron where pao player is the loser -- normal scoring."""
        game_state = self._create_game_state()
        game_state.round_state.players[0].pao_seat = 1  # pao == loser
        hand_result_0 = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=["Daisangen"])
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=["Riichi"])

        apply_double_ron_score(
            game_state,
            winners=[(0, hand_result_0), (2, hand_result_2)],
            loser_seat=1,
        )

        # seat 0: pao == loser, normal: loser pays full 32000
        # seat 2: normal: loser pays 2000
        # seat 1 total: -34000
        assert game_state.round_state.players[0].score == 25000 + 32000
        assert game_state.round_state.players[1].score == 25000 - 34000
        assert game_state.round_state.players[2].score == 25000 + 2000
        assert game_state.round_state.players[3].score == 25000
