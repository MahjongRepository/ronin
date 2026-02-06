"""
Unit tests for double yakuman scoring.

Tests that suuankou tanki, daisuushii, daburu kokushi, and daburu chuuren poutou
score as double yakuman (26 han) while regular variants remain at single yakuman (13 han).
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import (
    HandResult,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
)
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


class TestDoubleYakumanRonScoring:
    """Double yakuman non-dealer ron costs 64000 points."""

    def test_non_dealer_double_yakuman_ron_payment(self):
        game_state = _create_game_state()
        # simulate double yakuman ron result
        hand_result = HandResult(han=26, fu=0, cost_main=64000, cost_additional=0, yaku=["Suuankou Tanki"])

        new_round_state, _new_game_state, _result = apply_ron_score(
            game_state, winner_seat=1, loser_seat=2, hand_result=hand_result
        )

        assert new_round_state.players[1].score == 25000 + 64000
        assert new_round_state.players[2].score == 25000 - 64000
        assert new_round_state.players[0].score == 25000
        assert new_round_state.players[3].score == 25000

    def test_dealer_double_yakuman_ron_payment(self):
        game_state = _create_game_state()
        # dealer double yakuman ron = 96000
        hand_result = HandResult(han=26, fu=0, cost_main=96000, cost_additional=0, yaku=["Daisuushii"])

        new_round_state, _new_game_state, _result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result
        )

        assert new_round_state.players[0].score == 25000 + 96000
        assert new_round_state.players[1].score == 25000 - 96000


class TestDoubleYakumanTsumoScoring:
    """Double yakuman tsumo payments are correct."""

    def test_non_dealer_double_yakuman_tsumo_payment(self):
        # non-dealer double yakuman tsumo: dealer pays 32000, each non-dealer pays 16000
        game_state = _create_game_state()
        hand_result = HandResult(
            han=26, fu=0, cost_main=32000, cost_additional=16000, yaku=["Suuankou Tanki"]
        )

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state, winner_seat=1, hand_result=hand_result
        )

        # winner receives 64000 total from three losers
        assert new_round_state.players[1].score == 25000 + 64000
        assert new_round_state.players[0].score == 25000 - 32000  # dealer
        assert new_round_state.players[2].score == 25000 - 16000  # non-dealer
        assert new_round_state.players[3].score == 25000 - 16000  # non-dealer

    def test_dealer_double_yakuman_tsumo_payment(self):
        # dealer double yakuman tsumo: each non-dealer pays 32000
        game_state = _create_game_state()
        hand_result = HandResult(han=26, fu=0, cost_main=32000, cost_additional=0, yaku=["Daisuushii"])

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        # winner receives 96000 total from three losers
        assert new_round_state.players[0].score == 25000 + 96000
        assert new_round_state.players[1].score == 25000 - 32000
        assert new_round_state.players[2].score == 25000 - 32000
        assert new_round_state.players[3].score == 25000 - 32000


class TestKazoeYakumanStaysSingle:
    """Kazoe yakuman (13+ han from regular yaku) stays at single yakuman level."""

    def test_kazoe_yakuman_is_single(self):
        # kazoe yakuman: 13+ han from regular yaku, capped at single yakuman
        # non-dealer ron: 32000 (single yakuman)
        game_state = _create_game_state()
        hand_result = HandResult(han=13, fu=0, cost_main=32000, cost_additional=0, yaku=["Riichi", "Dora 12"])

        new_round_state, _new_game_state, _result = apply_ron_score(
            game_state, winner_seat=1, loser_seat=2, hand_result=hand_result
        )

        assert new_round_state.players[1].score == 25000 + 32000
        assert new_round_state.players[2].score == 25000 - 32000
