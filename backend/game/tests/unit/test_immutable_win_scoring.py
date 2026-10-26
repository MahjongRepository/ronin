from mahjong.hand_calculating.yaku_list.yakuman import Daisangen
from mahjong.tile import TilesConverter

from game.logic.enums import RoundResultType
from game.logic.round import (
    process_exhaustive_draw,
)
from game.logic.scoring import (
    HandResult,
    ScoringContext,
    apply_double_ron_score,
    calculate_hand_value,
)
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.types import YakuInfo
from game.logic.win import can_call_ron
from game.tests.helpers.wall import make_wall


class TestCanCallRonFuritenGuards:
    def _create_ron_state(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        dora_tiles = TilesConverter.string_to_136_array(man="1")
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1235")

        players_list = list(players)
        players_list[0] = players_list[0].model_copy(update={"tiles": tuple(tiles), "is_riichi": True})
        round_state = MahjongRoundState(
            dealer_seat=0,
            players=tuple(players_list),
            wall=make_wall(dora_indicators=tuple(dora_tiles)),
            all_discards=tuple(TilesConverter.string_to_136_array(man="1112")),
        )
        win_tile = TilesConverter.string_to_136_array(pin="5")[0]
        return round_state, win_tile

    def test_can_call_ron__when_riichi_furiten__should_return_false(self):
        round_state, win_tile = self._create_ron_state()
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"is_riichi_furiten": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        settings = GameSettings()
        result = can_call_ron(
            round_state.players[0], discarded_tile=win_tile, round_state=round_state, settings=settings
        )
        assert result is False

    def test_can_call_ron__when_temporary_furiten__should_return_false(self):
        round_state, win_tile = self._create_ron_state()
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"is_temporary_furiten": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        settings = GameSettings()
        result = can_call_ron(
            round_state.players[0], discarded_tile=win_tile, round_state=round_state, settings=settings
        )
        assert result is False


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


class TestApplyDoubleRonWithPao:
    def test_apply_double_ron_score__when_one_winner_owes_pao_to_the_other__should_report_each_value_and_payment(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        players_list = list(players)
        players_list[2] = players_list[2].model_copy(update={"pao_seat": 1})
        round_state = MahjongRoundState(wall=make_wall(), dealer_seat=0, players=tuple(players_list))
        game_state = MahjongGameState(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        mangan = HandResult(han=5, fu=30, cost_main=8000, yaku=[YakuInfo(yaku_id=0, han=5)])
        yakuman = HandResult(han=13, fu=30, cost_main=32000, yaku=[YakuInfo(yaku_id=Daisangen.yaku_id, han=13)])

        _new_game, result = apply_double_ron_score(
            game_state,
            winners=[(1, mangan), (2, yakuman)],
            loser_seat=0,
            winning_tile=0,
        )
        assert result.score_changes == {0: -24000, 1: -8000, 2: 32000, 3: 0}
        assert [w.hand_result.points for w in result.winners] == [8000, 32000]
        assert [w.score_changes for w in result.winners] == [
            {0: -8000, 1: 8000, 2: 0, 3: 0},
            {0: -16000, 1: -16000, 2: 32000, 3: 0},
        ]


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


class TestCalculateHandValueErrors:
    def _create_round_state(self) -> MahjongRoundState:
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        return MahjongRoundState(
            dealer_seat=0,
            round_wind=0,
            players=tuple(MahjongPlayer(seat=i, name=f"P{i}", score=25000) for i in range(4)),
            wall=make_wall(dead_wall=dead_wall, dora_indicators=(dead_wall[2],)),
        )

    def test_calculate_hand_value__when_hand_is_invalid__should_return_error(self):
        round_state = self._create_round_state()
        # incomplete hand (only 5 tiles) — no valid yaku possible
        bad_tiles = TilesConverter.string_to_136_array(man="12345")
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(bad_tiles), score=25000)

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, bad_tiles[0])
        assert result.error is not None
