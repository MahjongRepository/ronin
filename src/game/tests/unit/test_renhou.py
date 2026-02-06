"""
Unit tests for renhou (blessing of man) detection and scoring.
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import calculate_hand_value
from game.logic.state import Discard
from game.logic.state_utils import update_player
from game.logic.win import is_renhou
from game.tests.conftest import create_game_state, create_player, create_round_state


class TestIsRenhou:
    def _create_round_state(self, dealer_seat: int = 0):
        """
        Create a round state for renhou testing.

        No discards and no melds (first go-around conditions).
        """
        players = tuple(create_player(seat=i) for i in range(4))
        return create_round_state(
            players=players,
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
            all_discards=(),
            players_with_open_hands=(),
        )

    def test_renhou_non_dealer_first_goaround(self):
        # non-dealer player with no discards, no calls by anyone
        round_state = self._create_round_state(dealer_seat=0)
        player = round_state.players[1]  # seat 1, non-dealer
        assert is_renhou(player, round_state) is True

    def test_renhou_seat_2_non_dealer(self):
        # another non-dealer seat
        round_state = self._create_round_state(dealer_seat=0)
        player = round_state.players[2]
        assert is_renhou(player, round_state) is True

    def test_renhou_seat_3_non_dealer(self):
        round_state = self._create_round_state(dealer_seat=0)
        player = round_state.players[3]
        assert is_renhou(player, round_state) is True

    def test_not_renhou_dealer(self):
        # dealer cannot have renhou
        round_state = self._create_round_state(dealer_seat=0)
        player = round_state.players[0]  # dealer
        assert is_renhou(player, round_state) is False

    def test_not_renhou_dealer_at_seat_2(self):
        # dealer at seat 2 cannot have renhou
        round_state = self._create_round_state(dealer_seat=2)
        player = round_state.players[2]  # dealer
        assert is_renhou(player, round_state) is False

    def test_not_renhou_after_open_meld(self):
        # a player called an open meld (pon/chi)
        round_state = self._create_round_state(dealer_seat=0)
        round_state = round_state.model_copy(update={"players_with_open_hands": (2,)})  # seat 2 has open hand
        player = round_state.players[1]
        assert is_renhou(player, round_state) is False

    def test_not_renhou_after_closed_kan(self):
        # a closed kan was made (adds to player's melds)
        round_state = self._create_round_state(dealer_seat=0)
        kan_tiles = TilesConverter.string_to_136_array(man="1111")
        closed_kan = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(kan_tiles), opened=False)
        round_state = update_player(round_state, 0, melds=(closed_kan,))
        player = round_state.players[1]
        assert is_renhou(player, round_state) is False

    def test_not_renhou_player_has_discards(self):
        # player already discarded (past their first turn)
        round_state = self._create_round_state(dealer_seat=0)
        tile = TilesConverter.string_to_136_array(man="1")[0]
        round_state = update_player(round_state, 1, discards=(Discard(tile_id=tile),))
        player = round_state.players[1]
        assert is_renhou(player, round_state) is False

    def test_renhou_other_player_has_discards_but_winner_does_not(self):
        # other players may have discarded, but the winner has not
        # renhou checks: no calls, winner has no discards
        # note: all_discards tracks global discards, but is_renhou only
        # checks player.discards (player's own discard list)
        round_state = self._create_round_state(dealer_seat=0)
        # dealer discarded a tile (this is the tile the winner is ron-ing on)
        tile = TilesConverter.string_to_136_array(man="1")[0]
        round_state = update_player(round_state, 0, discards=(Discard(tile_id=tile),))
        round_state = round_state.model_copy(update={"all_discards": (tile,)})
        player = round_state.players[1]  # non-dealer, no discards
        assert is_renhou(player, round_state) is True

    def test_not_renhou_any_player_has_melds(self):
        # even if the winner has no melds, if another player has a meld, no renhou
        round_state = self._create_round_state(dealer_seat=0)
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        open_pon = FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(pon_tiles), opened=True)
        round_state = update_player(round_state, 3, melds=(open_pon,))
        round_state = round_state.model_copy(update={"players_with_open_hands": (3,)})
        player = round_state.players[1]
        assert is_renhou(player, round_state) is False


class TestRenhouScoring:
    def _create_game_state(self, dealer_seat: int = 0):
        """
        Create a game state for renhou scoring tests.

        First go-around conditions: no discards, no melds.
        """
        players = tuple(create_player(seat=i) for i in range(4))
        dora_indicator_tiles = TilesConverter.string_to_136_array(man="9")
        round_state = create_round_state(
            players=players,
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
            dora_indicators=dora_indicator_tiles,
            wall=tuple(range(70)),
            dead_wall=tuple(range(14)),
            all_discards=(),
            players_with_open_hands=(),
        )
        return create_game_state(round_state=round_state)

    def test_renhou_scores_5_han(self):
        # non-dealer ron on first go-around: renhou = 5 han
        # hand: 234m 234p 234s 678s 11z (no ittsu, no aka dora)
        # win tile: 1z (east wind pair, but player is south wind)
        tiles = TilesConverter.string_to_136_array(man="234", pin="234", sou="234678", honors="11")
        game_state = self._create_game_state(dealer_seat=0)
        round_state = update_player(game_state.round_state, 1, tiles=tuple(tiles))  # seat 1 = south wind
        player = round_state.players[1]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert "Renhou" in result.yaku
        # renhou 5 han is the primary yaku
        assert result.han >= 5

    def test_renhou_is_mangan_minimum(self):
        # renhou alone is 5 han = mangan
        # hand: 234m 567m 234p 567s 55s (tanyao + pinfu + renhou)
        # tanyao = 1 han, pinfu = 1 han, renhou = 5 han = 7 han (haneman)
        tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="56755")
        game_state = self._create_game_state(dealer_seat=0)
        round_state = update_player(game_state.round_state, 1, tiles=tuple(tiles))
        player = round_state.players[1]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert "Renhou" in result.yaku
        assert result.han >= 5

    def test_no_renhou_for_dealer_ron(self):
        # dealer cannot get renhou, even on first go-around
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state(dealer_seat=0)
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles))  # dealer
        player = round_state.players[0]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        # renhou should not be in yaku list
        assert "Renhou" not in result.yaku

    def test_no_renhou_after_calls(self):
        # a call was made before the ron: no renhou
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state(dealer_seat=0)
        # simulate a call having been made
        pon_tiles = TilesConverter.string_to_136_array(sou="111")
        open_pon = FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(pon_tiles), opened=True)
        round_state = update_player(game_state.round_state, 1, tiles=tuple(tiles))
        round_state = update_player(round_state, 3, melds=(open_pon,))
        round_state = round_state.model_copy(update={"players_with_open_hands": (3,)})
        player = round_state.players[1]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert "Renhou" not in result.yaku

    def test_no_renhou_after_closed_kan(self):
        # a closed kan was made: no renhou
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state(dealer_seat=0)
        # closed kan by dealer
        kan_tiles = TilesConverter.string_to_136_array(sou="1111")
        closed_kan = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(kan_tiles), opened=False)
        round_state = update_player(game_state.round_state, 1, tiles=tuple(tiles))
        round_state = update_player(round_state, 0, melds=(closed_kan,))
        player = round_state.players[1]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert "Renhou" not in result.yaku

    def test_no_renhou_player_already_discarded(self):
        # player has already discarded (past first turn): no renhou
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state(dealer_seat=0)
        # player already made a discard
        discard_tile = TilesConverter.string_to_136_array(sou="9")[0]
        round_state = update_player(
            game_state.round_state, 1, tiles=tuple(tiles), discards=(Discard(tile_id=discard_tile),)
        )
        # need some discards in all_discards to avoid library treating it as first go-around
        round_state = round_state.model_copy(update={"all_discards": (discard_tile,)})
        player = round_state.players[1]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert "Renhou" not in result.yaku

    def test_renhou_combines_with_other_yaku(self):
        # renhou + tanyao should combine han values
        # 234m 234p 234s 678m 33s (all simples, no terminals/honors)
        # win tile: 3s (two-sided wait on 23s -> completes 234s pair)
        tiles = TilesConverter.string_to_136_array(man="234678", pin="234", sou="23433")
        game_state = self._create_game_state(dealer_seat=0)
        round_state = update_player(game_state.round_state, 1, tiles=tuple(tiles))
        player = round_state.players[1]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert "Renhou" in result.yaku
        # renhou 5 han + at least tanyao 1 han
        assert result.han >= 6

    def test_no_renhou_on_tsumo(self):
        # renhou is ron-only; tsumo on first draw would be chiihou (for non-dealer)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = self._create_game_state(dealer_seat=0)
        round_state = update_player(game_state.round_state, 1, tiles=tuple(tiles))
        player = round_state.players[1]
        win_tile = tiles[-1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=True)

        assert result.error is None
        # tsumo on first go-around = chiihou, not renhou
        assert "Renhou" not in result.yaku
