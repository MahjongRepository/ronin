import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import RoundResultType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import (
    HandResult,
    ScoringContext,
    apply_double_ron_score,
    apply_nagashi_mangan_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
    calculate_hand_value_with_tiles,
    collect_ura_dora_indicators,
)
from game.logic.settings import GameSettings
from game.logic.state import (
    MahjongGameState,
    seat_to_wind,
)
from game.logic.state_utils import update_player
from game.logic.tiles import EAST_34, NORTH_34, SOUTH_34, WEST_34
from game.logic.types import YakuInfo
from game.tests.conftest import create_game_state, create_player, create_round_state


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


def _create_scoring_game_state(dealer_seat: int = 0, round_wind: int = 0) -> MahjongGameState:
    players = tuple(create_player(seat=i) for i in range(4))
    dora_indicator_tiles = TilesConverter.string_to_136_array(man="1")
    dummy_discard_tiles = TilesConverter.string_to_136_array(man="1112")
    round_state = create_round_state(
        players=players,
        dealer_seat=dealer_seat,
        current_player_seat=0,
        round_wind=round_wind,
        dora_indicators=dora_indicator_tiles,  # 1m as dora indicator (makes 2m dora)
        wall=tuple(range(70)),  # some tiles in wall (not empty)
        dead_wall=tuple(range(14)),  # dummy dead wall for ura dora
        all_discards=dummy_discard_tiles,  # some discards to avoid tenhou/chiihou
    )
    return create_game_state(round_state=round_state)


class TestSeatToWind:
    def test_seat_to_wind__when_dealer_at_seat_2__should_wrap_winds_around_table(self):
        # dealer at seat 2: seat 2=East, seat 3=South, seat 0=West, seat 1=North
        assert seat_to_wind(2, 2) == EAST_34
        assert seat_to_wind(3, 2) == SOUTH_34
        assert seat_to_wind(0, 2) == WEST_34
        assert seat_to_wind(1, 2) == NORTH_34


class TestCalculateHandValue:
    def test_calculate_hand_value__when_closed_pinfu_tsumo__should_return_scored_result(self):
        # 123m 456m 789m 123p 55p - pinfu tsumo
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles))
        player = round_state.players[0]

        win_tile = tiles[-1]  # 5p
        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han >= 1  # at least menzen tsumo
        assert result.fu > 0
        assert result.cost_main > 0
        assert len(result.yaku) > 0

    def test_calculate_hand_value__when_riichi_tsumo__should_include_riichi_yaku(self):
        # closed hand with riichi
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han >= 2  # riichi + menzen tsumo
        assert any(y.yaku_id == 1 for y in result.yaku)  # Riichi

    def test_calculate_hand_value__when_riichi_ron__should_not_include_menzen_tsumo(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han >= 1  # riichi
        assert not any(y.yaku_id == 0 for y in result.yaku)  # no Menzen Tsumo

    def test_calculate_hand_value__when_open_hand_has_no_yaku__should_return_no_yaku_error(self):
        # open hand with no yaku
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        win_tile = TilesConverter.string_to_136_array(man="5")[:1]
        all_tiles = tuple(closed_tiles + pon_tiles + win_tile)

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=all_tiles, melds=(pon,))
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile[0])

        assert result.error == "no_yaku"

    def test_calculate_hand_value__when_open_hand_ron_with_meld_tiles_outside_hand__should_score_yakuhai(self):
        # after meld call in actual gameplay, meld tiles are removed from player.tiles
        # closed: 234m 567m 23s 55s (10 tiles) + PON(Haku) (meld) = 13 total
        # ron on 4s to complete: 234m 567m 234s 55s + PON(Haku) = 14 total
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

        game_state = _create_scoring_game_state()
        # only closed tiles in hand (matching actual gameplay after meld call)
        # add ron tile
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        all_tiles = (*tuple(closed_tiles), win_tile)
        round_state = update_player(game_state.round_state, 0, tiles=all_tiles, melds=(pon,))
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han >= 1  # yakuhai (haku)
        assert result.cost_main > 0


class TestApplyTsumoScore:
    def _create_game_state(self) -> MahjongGameState:
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_apply_tsumo_score__when_dealer_tsumo__should_charge_each_player_equally(self):
        # dealer wins with 30fu 2han = 2000 all (dealer tsumo)
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state,
            winner_seat=0,
            hand_result=hand_result,
        )

        # dealer (seat 0) gets 6000 total (2000 * 3)
        assert new_round_state.players[0].score == 25000 + 6000
        # each non-dealer pays 2000
        assert new_round_state.players[1].score == 25000 - 2000
        assert new_round_state.players[2].score == 25000 - 2000
        assert new_round_state.players[3].score == 25000 - 2000

    def test_apply_tsumo_score__when_honba__should_add_100_per_honba_to_each_loser(self):
        # tsumo with 2 honba sticks = +200 total (100 per loser)
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state,
            winner_seat=1,
            hand_result=hand_result,
        )

        # winner gets 2000 + 600 (300 * 2 honba, but per-loser so 100*2*3=600)
        assert new_round_state.players[1].score == 25000 + 2600
        # dealer pays 1000 + 200
        assert new_round_state.players[0].score == 25000 - 1200
        # non-dealers pay 500 + 200
        assert new_round_state.players[2].score == 25000 - 700
        assert new_round_state.players[3].score == 25000 - 700

    def test_apply_tsumo_score__when_riichi_sticks__should_award_and_clear_them(self):
        # tsumo with 2 riichi sticks on table
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_round_state, new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=1,
            hand_result=hand_result,
        )

        # winner gets 2000 + 2000 (riichi sticks)
        assert new_round_state.players[1].score == 25000 + 4000
        # riichi sticks should be cleared
        assert new_game_state.riichi_sticks == 0
        assert result.riichi_sticks_collected == 2

    def test_apply_tsumo_score__should_exclude_win_tile_from_closed_tiles(self):
        # Player hand: tiles [0,1,2,3] where 3 is the drawn (winning) tile
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=0,
            hand_result=hand_result,
        )

        assert result.win_tile == 3
        assert result.win_tile not in result.closed_tiles
        assert result.closed_tiles == [0, 1, 2]

    def test_apply_tsumo_score__when_winner_in_riichi__should_report_ura_dora_indicators(self):
        dead_wall = tuple(range(100, 114))
        dora_indicators = (dead_wall[2],)
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], is_riichi=(i == 0)) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            dead_wall=dead_wall,
            dora_indicators=dora_indicators,
        )
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=0,
            hand_result=hand_result,
        )

        assert result.ura_dora_indicators == [dead_wall[7]]


class TestApplyRonScore:
    def _create_game_state(self) -> MahjongGameState:
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_apply_ron_score__when_honba__should_add_300_per_honba_to_payment(self):
        # ron with 3 honba sticks = +900 total
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 3})
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        # winner gets 2000 + 900
        assert new_round_state.players[0].score == 25000 + 2900
        # loser pays 2000 + 900
        assert new_round_state.players[1].score == 25000 - 2900

    def test_apply_ron_score__when_riichi_sticks__should_award_them_to_winner_only(self):
        # ron with 3 riichi sticks
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 3})
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_round_state, new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        # winner gets 2000 + 3000
        assert new_round_state.players[0].score == 25000 + 5000
        # loser only pays 2000
        assert new_round_state.players[1].score == 25000 - 2000
        # riichi sticks cleared
        assert new_game_state.riichi_sticks == 0
        assert result.riichi_sticks_collected == 3

    def test_apply_ron_score__when_winner_in_riichi__should_report_ura_dora_indicators(self):
        dead_wall = tuple(range(100, 114))
        dora_indicators = (dead_wall[2],)
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], is_riichi=(i == 0)) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            dead_wall=dead_wall,
            dora_indicators=dora_indicators,
        )
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        assert result.ura_dora_indicators == [dead_wall[7]]


class TestApplyDoubleRonScore:
    def _create_game_state(self) -> MahjongGameState:
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_apply_double_ron_score__when_two_winners__should_charge_loser_both_hands(self):
        # two winners ron off one discard
        game_state = self._create_game_state()
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, _new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=55,
        )

        # seat 0 wins 2000
        assert new_round_state.players[0].score == 25000 + 2000
        # seat 2 wins 4000
        assert new_round_state.players[2].score == 25000 + 4000
        # seat 1 pays 6000 total
        assert new_round_state.players[1].score == 25000 - 6000
        # seat 3 unaffected
        assert new_round_state.players[3].score == 25000
        assert result.type == RoundResultType.DOUBLE_RON
        assert result.winning_tile == 55

    def test_apply_double_ron_score__when_honba__should_add_honba_for_each_winner(self):
        # both winners get honba bonus
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 2})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, _new_game_state, _result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=0,
        )

        # each winner gets 2000 + 600 honba
        assert new_round_state.players[0].score == 25000 + 2600
        assert new_round_state.players[2].score == 25000 + 2600
        # loser pays both (2000+600)*2 = 5200
        assert new_round_state.players[1].score == 25000 - 5200

    def test_apply_double_ron_score__when_riichi_sticks__should_award_them_to_winner_closest_after_loser(self):
        # riichi sticks go to winner closest to loser's right (counter-clockwise)
        # loser is seat 1, checking seats 2, 3, 0 in order
        # if winners are 0 and 2, seat 2 is checked first
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=0,
        )

        # seat 2 is closer (loser_seat + 1 = seat 2)
        # seat 2 gets 2000 + 2000 riichi
        assert new_round_state.players[2].score == 25000 + 4000
        # seat 0 only gets 2000
        assert new_round_state.players[0].score == 25000 + 2000
        # riichi sticks cleared
        assert new_game_state.riichi_sticks == 0

        # verify which winner got riichi sticks
        for w in result.winners:
            if w.winner_seat == 2:
                assert w.riichi_sticks_collected == 2
            else:
                assert w.riichi_sticks_collected == 0

    def test_apply_double_ron_score__when_loser_seat_3__should_award_sticks_to_seat_0(self):
        # different loser seat changes who gets riichi
        # loser is seat 3, checking seats 0, 1, 2 in order
        # if winners are 0 and 2, seat 0 is checked first
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 1})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, _new_game_state, _result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=3,
            winning_tile=0,
        )

        # seat 0 is closer (loser_seat + 1 = seat 0)
        # seat 0 gets 2000 + 1000 riichi
        assert new_round_state.players[0].score == 25000 + 3000
        # seat 2 only gets 2000
        assert new_round_state.players[2].score == 25000 + 2000

    def test_apply_double_ron_score__when_one_winner_in_riichi__should_report_ura_dora_only_for_them(self):
        dead_wall = tuple(range(100, 114))
        dora_indicators = (dead_wall[2],)
        # seat 0 is riichi, seat 2 is not
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], is_riichi=(i == 0)) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            dead_wall=dead_wall,
            dora_indicators=dora_indicators,
        )
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        _new_round_state, _new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=0,
        )

        for w in result.winners:
            if w.winner_seat == 0:
                assert w.ura_dora_indicators == [dead_wall[7]]
            else:
                assert w.ura_dora_indicators is None

    def test_apply_double_ron_score__when_no_winners__should_raise(self):
        game_state = self._create_game_state()
        with pytest.raises(ValueError, match="No riichi receiver found"):
            apply_double_ron_score(
                game_state,
                winners=[],
                loser_seat=1,
                winning_tile=0,
            )


class TestApplyNagashiManganScore:
    def _create_game_state(self, dealer_seat: int = 0) -> MahjongGameState:
        # use non-tempai hands (disconnected tiles) by default
        non_tempai_tiles = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")
        players = tuple(create_player(seat=i, score=25000, tiles=tuple(non_tempai_tiles)) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_apply_nagashi_mangan_score__when_dealer_qualifies__should_collect_4000_from_each(self):
        game_state = self._create_game_state(dealer_seat=0)

        new_round_state, _new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )

        assert result.type == RoundResultType.NAGASHI_MANGAN
        assert result.qualifying_seats == [0]
        assert result.score_changes[0] == 12000
        assert result.score_changes[1] == -4000
        assert result.score_changes[2] == -4000
        assert result.score_changes[3] == -4000
        assert new_round_state.players[0].score == 37000
        assert new_round_state.players[1].score == 21000
        assert new_round_state.players[2].score == 21000
        assert new_round_state.players[3].score == 21000

    def test_apply_nagashi_mangan_score__when_non_dealer_qualifies__should_charge_dealer_4000_and_others_2000(self):
        game_state = self._create_game_state(dealer_seat=0)

        new_round_state, _new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[1],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )

        assert result.score_changes[1] == 8000
        assert result.score_changes[0] == -4000  # dealer pays 4000
        assert result.score_changes[2] == -2000  # non-dealer pays 2000
        assert result.score_changes[3] == -2000  # non-dealer pays 2000
        assert new_round_state.players[1].score == 33000
        assert new_round_state.players[0].score == 21000
        assert new_round_state.players[2].score == 23000
        assert new_round_state.players[3].score == 23000

    def test_apply_nagashi_mangan_score__when_two_players_qualify__should_net_payments_to_zero_sum(self):
        game_state = self._create_game_state(dealer_seat=0)

        _new_round_state, _new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0, 2],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
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


class TestPaoTsumoScoring:
    def _create_game_state(self) -> MahjongGameState:
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_pao__when_non_dealer_yakuman_tsumo__should_charge_pao_player_everything(self):
        game_state = self._create_game_state()
        # seat 1 wins with pao on seat 2
        # yakuman tsumo: dealer pays 16000, non-dealer pays 8000 each
        round_state = update_player(game_state.round_state, 1, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=1,
            hand_result=hand_result,
        )

        # total would be: 16000 (from dealer) + 8000 + 8000 = 32000
        # pao player (seat 2) pays all 32000
        assert result.pao_seat == 2
        assert new_round_state.players[0].score == 25000  # dealer pays nothing
        assert new_round_state.players[1].score == 25000 + 32000  # winner gets all
        assert new_round_state.players[2].score == 25000 - 32000  # pao pays all
        assert new_round_state.players[3].score == 25000  # other pays nothing

    def test_pao__when_dealer_yakuman_tsumo__should_charge_pao_player_everything(self):
        game_state = self._create_game_state()
        # seat 0 (dealer) wins with pao on seat 3
        # dealer yakuman tsumo: each non-dealer pays 16000
        round_state = update_player(game_state.round_state, 0, pao_seat=3)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=0,
            hand_result=hand_result,
        )

        # total would be: 16000 * 3 = 48000
        assert result.pao_seat == 3
        assert new_round_state.players[0].score == 25000 + 48000
        assert new_round_state.players[1].score == 25000
        assert new_round_state.players[2].score == 25000
        assert new_round_state.players[3].score == 25000 - 48000

    def test_pao__when_tsumo_with_riichi_sticks__should_give_sticks_to_winner(self):
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 1, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "riichi_sticks": 2})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=1,
            hand_result=hand_result,
        )

        # total tsumo: 32000 + 2000 riichi bonus
        assert new_round_state.players[1].score == 25000 + 34000
        assert new_round_state.players[2].score == 25000 - 32000
        assert result.riichi_sticks_collected == 2

    def test_pao__when_tsumo_with_honba__should_charge_honba_to_pao_player(self):
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 1, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "honba_sticks": 2})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state,
            winner_seat=1,
            hand_result=hand_result,
        )

        # honba: 100 per loser * 2 sticks = 200 per loser, 600 total
        # total normal: 32000 + 600 honba = 32600
        assert new_round_state.players[1].score == 25000 + 32600
        assert new_round_state.players[2].score == 25000 - 32600


class TestPaoRonScoring:
    def _create_game_state(self) -> MahjongGameState:
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_pao__when_ron_on_other_player__should_split_payment_with_pao_player(self):
        game_state = self._create_game_state()
        # seat 0 wins by ron off seat 1, pao on seat 2
        round_state = update_player(game_state.round_state, 0, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        # 32000 split: loser pays 16000, pao pays 16000
        assert result.pao_seat == 2
        assert new_round_state.players[0].score == 25000 + 32000
        assert new_round_state.players[1].score == 25000 - 16000
        assert new_round_state.players[2].score == 25000 - 16000
        assert new_round_state.players[3].score == 25000

    def test_pao__when_ron_on_pao_player__should_charge_them_in_full(self):
        game_state = self._create_game_state()
        # seat 0 wins by ron off seat 1, pao also on seat 1
        round_state = update_player(game_state.round_state, 0, pao_seat=1)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        # pao == loser: normal ron, loser pays full
        assert result.pao_seat == 1
        assert new_round_state.players[0].score == 25000 + 32000
        assert new_round_state.players[1].score == 25000 - 32000
        assert new_round_state.players[2].score == 25000
        assert new_round_state.players[3].score == 25000

    def test_pao__when_ron_with_honba__should_split_honba_between_payers(self):
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 0, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "honba_sticks": 2})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        # total: 32000 + 600 honba = 32600, split: 16300 each
        assert new_round_state.players[0].score == 25000 + 32600
        assert new_round_state.players[1].score == 25000 - 16300
        assert new_round_state.players[2].score == 25000 - 16300

    def test_pao__when_ron_with_riichi_sticks__should_give_sticks_to_winner(self):
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 0, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "riichi_sticks": 1})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        # 32000 split: loser 16000, pao 16000; winner also gets 1000 riichi
        assert new_round_state.players[0].score == 25000 + 33000
        assert new_round_state.players[1].score == 25000 - 16000
        assert new_round_state.players[2].score == 25000 - 16000
        assert result.riichi_sticks_collected == 1


class TestPaoRonScoreConservation:
    def _create_game_state(self) -> MahjongGameState:
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_pao__when_ron_on_other_player__should_sum_score_changes_to_zero(self):
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 0, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )

        assert sum(result.score_changes.values()) == 0


class TestChankanYakuScoring:
    def test_calculate_hand_value__when_chankan__should_include_chankan_yaku(self):
        # setup: player with riichi hand waiting on a tile
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]  # 5p
        settings = GameSettings()
        ctx = ScoringContext(
            player=player,
            round_state=round_state,
            settings=settings,
            is_tsumo=False,
            is_chankan=True,
        )
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert any(y.yaku_id == 4 for y in result.yaku)  # Chankan
        # riichi + chankan = 2 han
        assert result.han >= 2

    def test_calculate_hand_value__when_open_hand_chankan__should_score_with_chankan_as_only_yaku(self):
        # setup: open hand with pon of 1m (no yaku)
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[2],
            who=0,
            from_who=1,
        )
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")

        game_state = _create_scoring_game_state()
        # add win tile (5m)
        win_tile = TilesConverter.string_to_136_array(man="5")[0]
        all_tiles = (*tuple(closed_tiles), win_tile)
        round_state = update_player(game_state.round_state, 0, tiles=all_tiles, melds=(pon,))
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(
            player=player,
            round_state=round_state,
            settings=settings,
            is_tsumo=False,
            is_chankan=True,
        )
        result = calculate_hand_value(ctx, win_tile)

        # chankan provides the yaku, hand should succeed
        assert result.error is None
        assert any(y.yaku_id == 4 for y in result.yaku)  # Chankan
        assert result.han >= 1

    def test_calculate_hand_value__when_open_hand_ron_without_chankan_flag__should_return_no_yaku_error(self):
        # setup: same open hand as above
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[2],
            who=0,
            from_who=1,
        )
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")

        game_state = _create_scoring_game_state()
        # add win tile (5m)
        win_tile = TilesConverter.string_to_136_array(man="5")[0]
        all_tiles = (*tuple(closed_tiles), win_tile)
        round_state = update_player(game_state.round_state, 0, tiles=all_tiles, melds=(pon,))
        player = round_state.players[0]

        # call without is_chankan flag (default is False)
        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        # without chankan flag, the open hand has no yaku
        assert result.error == "no_yaku"


class TestHandValueParityBetweenFunctions:
    def test_calculate_hand_value_with_tiles__when_tsumo__should_match_calculate_hand_value(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles))
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result_a = calculate_hand_value(ctx, win_tile)
        result_b = calculate_hand_value_with_tiles(ctx, tiles, win_tile)

        assert result_a.han == result_b.han
        assert result_a.fu == result_b.fu
        assert result_a.cost_main == result_b.cost_main
        assert result_a.cost_additional == result_b.cost_additional
        assert result_a.yaku == result_b.yaku
        assert result_a.error == result_b.error

    def test_calculate_hand_value_with_tiles__when_no_yaku__should_match_calculate_hand_value_error(self):
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        win_tile = TilesConverter.string_to_136_array(man="5")[:1]
        all_tiles = tuple(closed_tiles + pon_tiles + win_tile)

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=all_tiles, melds=(pon,))
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result_a = calculate_hand_value(ctx, win_tile[0])
        result_b = calculate_hand_value_with_tiles(ctx, list(all_tiles), win_tile[0])

        assert result_a.error == result_b.error == "no_yaku"


class TestNagashiManganPreservesRiichiSticks:
    def test_apply_nagashi_mangan_score__when_riichi_sticks_on_table__should_keep_them(self):
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=3)

        _new_round_state, new_game_state, _result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        assert new_game_state.riichi_sticks == 3


class TestCollectUraDoraIndicators:
    def test_collect_ura_dora_indicators__when_dead_wall_empty__should_return_none(self):
        settings = GameSettings(has_uradora=True)
        round_state = create_round_state(
            dead_wall=(),
            dora_indicators=(10,),
        )
        player = create_player(seat=0, is_riichi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result is None

    def test_collect_ura_dora_indicators__when_no_dora_indicators__should_return_none(self):
        dead_wall = tuple(range(100, 114))
        settings = GameSettings(has_uradora=True)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(),
        )
        player = create_player(seat=0, is_riichi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result is None


class TestUraDoraScoringIntegration:
    def _build_game_state(self, *, dead_wall, dora_indicators, tiles, is_riichi):
        dummy_discard_tiles = TilesConverter.string_to_136_array(man="1112")
        players = tuple(
            create_player(
                seat=i,
                tiles=tuple(tiles) if i == 0 else None,
                is_riichi=is_riichi if i == 0 else False,
            )
            for i in range(4)
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            dora_indicators=dora_indicators,
            dead_wall=dead_wall,
            wall=tuple(range(70)),
            all_discards=dummy_discard_tiles,
        )
        return create_game_state(round_state=round_state)

    def test_calculate_hand_value__when_riichi_after_kan__should_count_ura_dora_for_each_indicator(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        # 2 dora indicators (simulating 1 kan)
        dora_indicator_1 = TilesConverter.string_to_136_array(man="1")[0]
        dora_indicator_2 = TilesConverter.string_to_136_array(man="5")[0]

        # ura dora 1: indicator 4s -> ura dora 5s (2 copies in hand = 2 han)
        # ura dora 2: indicator 1s -> ura dora 2s (1 copy in hand = 1 han)
        ura_tile_1 = TilesConverter.string_to_136_array(sou="4")[0]
        ura_tile_2 = TilesConverter.string_to_136_array(sou="1")[0]
        dead_wall = [0] * 14
        dead_wall[2] = dora_indicator_1
        dead_wall[3] = dora_indicator_2
        dead_wall[7] = ura_tile_1
        dead_wall[8] = ura_tile_2

        game_state = self._build_game_state(
            dead_wall=tuple(dead_wall),
            dora_indicators=(dora_indicator_1, dora_indicator_2),
            tiles=tiles,
            is_riichi=True,
        )
        player = game_state.round_state.players[0]
        settings = GameSettings(has_akadora=False, has_kan_uradora=True)
        ctx = ScoringContext(player=player, round_state=game_state.round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert any(y.yaku_id == 122 and y.han == 3 for y in result.yaku)  # Ura Dora 3
