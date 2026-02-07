"""
Unit tests for double yakuman hand recognition.

Tests that suuankou tanki and daisuushii are correctly identified as double yakuman (26 han)
while regular suuankou stays at single yakuman (13 han).
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import calculate_hand_value
from game.logic.state import MahjongGameState
from game.logic.state_utils import update_player
from game.tests.conftest import create_game_state, create_player, create_round_state


def _create_game_state(dealer_seat: int = 0) -> MahjongGameState:
    """
    Create a game state for scoring tests.

    Sets up a mid-game state (some discards) to avoid triggering tenhou/chiihou.
    """
    players = tuple(create_player(seat=i, score=25000) for i in range(4))
    dora_indicator_tiles = TilesConverter.string_to_136_array(man="1")
    dummy_discard_tiles = TilesConverter.string_to_136_array(man="1112")
    round_state = create_round_state(
        players=players,
        dealer_seat=dealer_seat,
        current_player_seat=0,
        round_wind=0,
        dora_indicators=dora_indicator_tiles,
        wall=tuple(range(70)),
        dead_wall=tuple(range(14)),
        all_discards=dummy_discard_tiles,
    )
    return create_game_state(round_state=round_state)


class TestSuuankouTankiDoubleYakuman:
    """Suuankou tanki (four concealed triplets, pair wait) scores as double yakuman."""

    def test_suuankou_tanki_tsumo_is_double_yakuman(self):
        # hand: 111m 333p 555s 777s + tanki (pair) wait on 9s
        tiles = TilesConverter.string_to_136_array(man="111", pin="333", sou="555777")
        pair_tiles = TilesConverter.string_to_136_array(sou="99")
        all_tiles = (*tuple(tiles), pair_tiles[0])

        game_state = _create_game_state()
        # win tile is the second 9s (completing the pair)
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles)  # non-dealer
        player = round_state.players[1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert result.han == 26
        assert result.cost_main == 32000  # dealer pays
        assert result.cost_additional == 16000  # each non-dealer pays

    def test_regular_suuankou_is_single_yakuman(self):
        # shanpon wait: 11m 333p 555s 777s 99s, waiting on 1m or 9s
        # winning on 1m completes a triplet (non-tanki wait) = regular suuankou
        man_tiles = TilesConverter.string_to_136_array(man="111")
        tiles = TilesConverter.string_to_136_array(pin="333", sou="555777")
        pair_tiles = TilesConverter.string_to_136_array(sou="99")
        all_tiles = tuple(man_tiles[:2]) + tuple(tiles) + tuple(pair_tiles)

        game_state = _create_game_state()
        # win on 1m (third copy, completing the triplet)
        win_tile = man_tiles[2]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles)  # non-dealer
        player = round_state.players[1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert result.han == 13
        assert result.cost_main == 16000
        assert result.cost_additional == 8000


class TestDaisuushiiDoubleYakuman:
    """Daisuushii (big four winds) scores as double yakuman."""

    def test_daisuushii_open_hand_is_double_yakuman(self):
        # open daisuushii: EEE(open) SSS WWW NNN + pair of 1m
        # use open pon of east wind to isolate from suuankou
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        closed_tiles = TilesConverter.string_to_136_array(honors="222333444")
        man_pair = TilesConverter.string_to_136_array(man="11")
        all_tiles = tuple(east_tiles) + tuple(closed_tiles) + (man_pair[0],)

        east_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(east_tiles),
            opened=True,
            called_tile=east_tiles[0],
            who=1,
            from_who=0,
        )

        game_state = _create_game_state()
        # win on second 1m (completing the pair)
        win_tile = man_pair[1]
        final_tiles = (*all_tiles, win_tile)
        # non-dealer
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles, melds=(east_pon,))
        player = round_state.players[1]

        result = calculate_hand_value(player, round_state, win_tile, is_tsumo=False)

        assert result.error is None
        assert result.han == 26
        assert result.cost_main == 64000  # non-dealer ron
