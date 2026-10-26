from mahjong.tile import TilesConverter

from game.logic.enums import RoundResultType
from game.logic.round import (
    process_exhaustive_draw,
)
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.tests.helpers.wall import make_wall


class TestProcessExhaustiveDrawPayment:
    def test_process_exhaustive_draw__when_one_tempai_and_three_noten__should_transfer_noten_payments(self):
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
        round_state = MahjongRoundState(players=players, wall=make_wall())
        game_state = MahjongGameState(round_state=round_state)

        new_game, result = process_exhaustive_draw(game_state)
        new_round = new_game.round_state
        assert result.tempai_seats == [0]
        assert result.noten_seats == [1, 2, 3]
        assert len(result.tenpai_hands) == 1
        assert result.tenpai_hands[0].seat == 0
        assert result.tenpai_hands[0].closed_tiles == list(tempai_hand)
        assert result.tenpai_hands[0].melds == []
        assert new_round.players[0].score == 28000
        assert new_round.players[1].score == 24000
        assert new_round.players[2].score == 24000
        assert new_round.players[3].score == 24000


class TestProcessExhaustiveDrawNagashiTriggered:
    def test_process_exhaustive_draw__when_only_terminal_honor_discards__should_pay_nagashi_mangan(self):
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
        players = (
            MahjongPlayer(seat=0, name="Player0", tiles=tempai_hand, score=25000, discards=nagashi_discards),
            MahjongPlayer(seat=1, name="Player1", tiles=non_tempai_hand, score=25000),
            MahjongPlayer(seat=2, name="Player2", tiles=non_tempai_hand, score=25000),
            MahjongPlayer(seat=3, name="Player3", tiles=non_tempai_hand, score=25000),
        )
        round_state = MahjongRoundState(players=players, wall=make_wall(), dealer_seat=1)
        game_state = MahjongGameState(round_state=round_state)

        new_game, result = process_exhaustive_draw(game_state)
        new_round = new_game.round_state
        # Nagashi mangan gives mangan payment (non-dealer: 2000/4000)
        # Player 0 is non-dealer: gets 2000 from each non-dealer + 4000 from dealer = 8000
        assert result.type == RoundResultType.NAGASHI_MANGAN
        assert new_round.players[0].score == 25000 + 8000
