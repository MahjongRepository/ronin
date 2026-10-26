import pytest
from mahjong.hand_calculating.yaku_list.yakuman import Daisangen, DaiSuushii, Tsuuiisou
from mahjong.tile import TilesConverter

from game.logic.enums import RoundPhase, RoundResultType
from game.logic.events import GameEvent, RoundEndEvent
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
)
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    seat_to_wind,
)
from game.logic.state_utils import update_player
from game.logic.tiles import EAST_34, NORTH_34, SOUTH_34, WEST_34
from game.logic.turn import process_ron_call, process_tsumo_call
from game.logic.types import DoubleRonResult, RonCallInput, RonResult, RoundResult, TsumoResult, YakuInfo
from game.tests.conftest import create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import FIRST_URA_POSITION


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


def _sum_winner_changes(result: DoubleRonResult) -> dict[int, int]:
    return {seat: sum(w.score_changes[seat] for w in result.winners) for seat in range(4)}


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
        dead_wall=(None, None, None, *range(3, 14)),
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
        assert [(y.yaku_id, y.han) for y in result.yaku] == [(0, 1), (27, 2), (120, 1), (121, 2)]
        assert (result.han, result.fu) == (6, 30)
        assert (result.cost_main, result.cost_additional) == (6000, 6000)

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
        assert [(y.yaku_id, y.han) for y in result.yaku] == [(0, 1), (1, 1), (27, 2), (120, 1), (121, 2), (122, 1)]
        assert result.han == 8

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
        assert [(y.yaku_id, y.han) for y in result.yaku] == [(1, 1), (27, 2), (120, 1), (121, 2), (122, 1)]
        assert result.han == 7

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
        assert [(y.yaku_id, y.han) for y in result.yaku] == [(15, 1), (120, 1), (121, 2)]
        assert (result.han, result.fu, result.cost_main) == (4, 30, 12000)


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

        new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=0,
            hand_result=hand_result,
        )
        new_round_state = new_game_state.round_state
        # dealer (seat 0) gets 6000 total (2000 * 3)
        assert new_round_state.players[0].score == 25000 + 6000
        # each non-dealer pays 2000
        assert new_round_state.players[1].score == 25000 - 2000
        assert new_round_state.players[2].score == 25000 - 2000
        assert new_round_state.players[3].score == 25000 - 2000
        assert result.hand_result.points == 6000

    def test_apply_tsumo_score__when_honba__should_add_100_per_honba_to_each_loser(self):
        # tsumo with 2 honba sticks = +200 total (100 per loser)
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=1,
            hand_result=hand_result,
        )
        new_round_state = new_game_state.round_state
        # winner gets 2000 + 600 (300 * 2 honba, but per-loser so 100*2*3=600)
        assert new_round_state.players[1].score == 25000 + 2600
        # dealer pays 1000 + 200
        assert new_round_state.players[0].score == 25000 - 1200
        # non-dealers pay 500 + 200
        assert new_round_state.players[2].score == 25000 - 700
        assert new_round_state.players[3].score == 25000 - 700
        assert result.hand_result.points == 2000

    def test_apply_tsumo_score__when_riichi_sticks__should_award_and_clear_them(self):
        # tsumo with 2 riichi sticks on table
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=1,
            hand_result=hand_result,
        )
        new_round_state = new_game_state.round_state
        # winner gets 2000 + 2000 (riichi sticks)
        assert new_round_state.players[1].score == 25000 + 4000
        # riichi sticks should be cleared
        assert new_game_state.riichi_sticks == 0
        assert result.riichi_sticks_collected == 2

    def test_apply_tsumo_score__should_exclude_win_tile_from_closed_tiles(self):
        # Player hand: tiles [0,1,2,3] where 3 is the drawn (winning) tile
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_game_state, result = apply_tsumo_score(
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

        _new_game_state, result = apply_tsumo_score(
            game_state,
            winner_seat=0,
            hand_result=hand_result,
        )
        assert result.ura_dora_indicators == [dead_wall[FIRST_URA_POSITION]]


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

        new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )
        new_round_state = new_game_state.round_state
        # winner gets 2000 + 900
        assert new_round_state.players[0].score == 25000 + 2900
        # loser pays 2000 + 900
        assert new_round_state.players[1].score == 25000 - 2900
        assert result.hand_result.points == 2000

    def test_apply_ron_score__when_riichi_sticks__should_award_them_to_winner_only(self):
        # ron with 3 riichi sticks
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 3})
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )
        new_round_state = new_game_state.round_state
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

        _new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=0,
            loser_seat=1,
            hand_result=hand_result,
            winning_tile=0,
        )
        assert result.ura_dora_indicators == [dead_wall[FIRST_URA_POSITION]]


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
        new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=55,
        )
        new_round_state = new_game_state.round_state
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
        new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=0,
        )
        new_round_state = new_game_state.round_state
        # each winner gets 2000 + 600 honba
        assert new_round_state.players[0].score == 25000 + 2600
        assert new_round_state.players[2].score == 25000 + 2600
        # loser pays both (2000+600)*2 = 5200
        assert new_round_state.players[1].score == 25000 - 5200
        assert {w.winner_seat: w.score_changes for w in result.winners} == {
            0: {0: 2600, 1: -2600, 2: 0, 3: 0},
            2: {0: 0, 1: -2600, 2: 2600, 3: 0},
        }
        assert _sum_winner_changes(result) == result.score_changes

    def test_apply_double_ron_score__when_riichi_sticks__should_award_them_to_winner_closest_after_loser(self):
        # riichi sticks go to winner closest to loser's right (counter-clockwise)
        # loser is seat 1, checking seats 2, 3, 0 in order
        # if winners are 0 and 2, seat 2 is checked first
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=0,
        )
        new_round_state = new_game_state.round_state
        # seat 2 is closer (loser_seat + 1 = seat 2)
        # seat 2 gets 2000 + 2000 riichi
        assert new_round_state.players[2].score == 25000 + 4000
        # seat 0 only gets 2000
        assert new_round_state.players[0].score == 25000 + 2000
        # riichi sticks cleared
        assert new_game_state.riichi_sticks == 0
        assert {w.winner_seat: w.riichi_sticks_collected for w in result.winners} == {0: 0, 2: 2}
        assert {w.winner_seat: w.score_changes for w in result.winners} == {
            0: {0: 2000, 1: -2000, 2: 0, 3: 0},
            2: {0: 0, 1: -2000, 2: 4000, 3: 0},
        }
        assert _sum_winner_changes(result) == result.score_changes

    def test_apply_double_ron_score__when_loser_seat_3__should_award_sticks_to_seat_0(self):
        # different loser seat changes who gets riichi
        # loser is seat 3, checking seats 0, 1, 2 in order
        # if winners are 0 and 2, seat 0 is checked first
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 1})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_game_state, _result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=3,
            winning_tile=0,
        )
        new_round_state = new_game_state.round_state
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
        _new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=1,
            winning_tile=0,
        )
        assert {w.winner_seat: w.ura_dora_indicators for w in result.winners} == {
            0: [dead_wall[FIRST_URA_POSITION]],
            2: None,
        }

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

        new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        new_round_state = new_game_state.round_state
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

        new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[1],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        new_round_state = new_game_state.round_state
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

        _new_game_state, result = apply_nagashi_mangan_score(
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


_DAISANGEN_WIN_TILE = tile_copies(1, sou="9")[0]
_DAISANGEN_TSUUIISOU_WIN_TILE = tile_copies(1, honors="2")[0]
_ITTSUU_SHANPON_HAND = (
    *tile_copies(0, man="123456789"),
    *TilesConverter.string_to_136_array(pin="11"),
    *tile_copies(2, sou="9"),
    *tile_copies(3, sou="9"),
)


def _honor_pons(seat: int, *, from_seat: int, honors: str) -> tuple[FrozenMeld, ...]:
    return tuple(
        FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=seat,
            from_who=from_seat,
        )
        for pon_tiles in (TilesConverter.string_to_136_array(honors=honor * 3) for honor in honors)
    )


def _daisangen_player(seat: int, *, pao_seat: int, closed_tiles: list[int]) -> MahjongPlayer:
    melds = _honor_pons(seat, from_seat=pao_seat, honors="567")
    return create_player(seat=seat, tiles=closed_tiles, melds=melds, pao_seat=pao_seat)


def _daisangen_tanki_player(seat: int, *, pao_seat: int) -> MahjongPlayer:
    return _daisangen_player(seat, pao_seat=pao_seat, closed_tiles=tile_copies(0, pin="234", sou="9"))


def _daisangen_tsuuiisou_tanki_player(seat: int, *, pao_seat: int) -> MahjongPlayer:
    east_triplet_and_south = TilesConverter.string_to_136_array(honors="1112")
    return _daisangen_player(seat, pao_seat=pao_seat, closed_tiles=east_triplet_and_south)


def _with_drawn_tile(player: MahjongPlayer, tile: int) -> MahjongPlayer:
    return player.model_copy(update={"tiles": (*player.tiles, tile)})


def _stage_pao_win(
    *,
    dealer_seat: int,
    winners: list[MahjongPlayer],
    current_seat: int,
    discarded_tile: int | None = None,
    honba_sticks: int = 0,
    riichi_sticks: int = 0,
    settings: GameSettings | None = None,
) -> MahjongGameState:
    winners_by_seat = {winner.seat: winner for winner in winners}
    filler_copies = iter((1, 2, 3))
    players = []
    for seat in range(4):
        if seat in winners_by_seat:
            players.append(winners_by_seat[seat])
            continue

        is_discarder = discarded_tile is not None and seat == current_seat
        discards = [Discard(tile_id=discarded_tile)] if is_discarder else []
        filler_hand = tile_copies(next(filler_copies), man="123456789", pin="5678")
        players.append(create_player(seat=seat, tiles=filler_hand, discards=discards))

    round_state = create_round_state(
        players=players,
        wall=tile_copies(0, sou="2345678"),
        dora_indicators=tile_copies(0, sou="1"),
        dealer_seat=dealer_seat,
        current_player_seat=current_seat,
        phase=RoundPhase.PLAYING,
    )
    return create_game_state(round_state, honba_sticks=honba_sticks, riichi_sticks=riichi_sticks, settings=settings)


def _round_result(events: list[GameEvent]) -> RoundResult:
    assert len(events) == 1
    assert isinstance(events[0], RoundEndEvent)
    return events[0].result


class TestPaoTsumoScoring:
    def test_pao__when_non_dealer_tsumo_with_honba__should_charge_pao_player_everything(self):
        winner = _with_drawn_tile(_daisangen_tanki_player(1, pao_seat=2), _DAISANGEN_WIN_TILE)
        game_state = _stage_pao_win(dealer_seat=0, winners=[winner], current_seat=1, honba_sticks=1, riichi_sticks=1)

        _new_state, events = process_tsumo_call(game_state, winner_seat=1)
        result = _round_result(events)
        assert isinstance(result, TsumoResult)
        assert result.pao_seat == 2
        assert result.hand_result.points == 32000
        assert result.score_changes == {0: 0, 1: 33300, 2: -32300, 3: 0}
        assert result.riichi_sticks_collected == 1

    def test_pao__when_dealer_tsumo_stacks_another_yakuman__should_charge_pao_player_only_the_pao_yakuman_and_honba(
        self,
    ):
        winner = _with_drawn_tile(_daisangen_tsuuiisou_tanki_player(0, pao_seat=3), _DAISANGEN_TSUUIISOU_WIN_TILE)
        game_state = _stage_pao_win(dealer_seat=0, winners=[winner], current_seat=0, honba_sticks=1)

        _new_state, events = process_tsumo_call(game_state, winner_seat=0)
        result = _round_result(events)
        assert isinstance(result, TsumoResult)
        assert [y.yaku_id for y in result.hand_result.yaku] == [Daisangen.yaku_id, Tsuuiisou.yaku_id]
        assert result.hand_result.points == 96000
        assert result.score_changes == {0: 96300, 1: -16000, 2: -16000, 3: -64300}


class TestPaoRonScoring:
    def test_pao__when_dealer_rons_off_other_player__should_split_hand_value_and_give_sticks_to_winner(self):
        winner = _daisangen_tanki_player(0, pao_seat=2)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=1,
            discarded_tile=_DAISANGEN_WIN_TILE,
            riichi_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[0], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=1),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.pao_seat == 2
        assert result.hand_result.points == 48000
        assert result.score_changes == {0: 49000, 1: -24000, 2: -24000, 3: 0}
        assert result.riichi_sticks_collected == 1

    def test_pao__when_ron_on_pao_player__should_charge_them_in_full(self):
        winner = _daisangen_tanki_player(1, pao_seat=3)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=3,
            discarded_tile=_DAISANGEN_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=3),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.pao_seat == 3
        assert result.hand_result.points == 32000
        assert result.score_changes == {0: 0, 1: 32300, 2: 0, 3: -32300}

    def test_pao__when_ron_off_another_player_with_honba__should_charge_the_whole_honba_to_the_pao_player(self):
        winner = _daisangen_tanki_player(1, pao_seat=3)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=2,
            discarded_tile=_DAISANGEN_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=2),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.hand_result.points == 32000
        assert result.score_changes == {0: 0, 1: 32300, 2: -16000, 3: -16300}

    def test_pao__when_dealer_ron_stacks_another_yakuman__should_charge_pao_player_half_the_pao_yakuman_and_honba(
        self,
    ):
        winner = _daisangen_tsuuiisou_tanki_player(0, pao_seat=3)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=1,
            discarded_tile=_DAISANGEN_TSUUIISOU_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[0], tile_id=_DAISANGEN_TSUUIISOU_WIN_TILE, discarder_seat=1),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert [y.yaku_id for y in result.hand_result.yaku] == [Daisangen.yaku_id, Tsuuiisou.yaku_id]
        assert result.hand_result.points == 96000
        assert result.score_changes == {0: 96300, 1: -72000, 2: 0, 3: -24300}

    def test_pao__when_double_yakuman_daisuushii_ron_stacks_tsuuiisou__should_weigh_the_pao_share_by_han(self):
        melds = (*_honor_pons(1, from_seat=0, honors="123"), *_honor_pons(1, from_seat=3, honors="4"))
        winner = create_player(seat=1, tiles=tile_copies(0, honors="5"), melds=melds, pao_seat=3)
        haku_win_tile = tile_copies(1, honors="5")[0]
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=2,
            discarded_tile=haku_win_tile,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=haku_win_tile, discarder_seat=2),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert [(y.yaku_id, y.han) for y in result.hand_result.yaku] == [
            (Tsuuiisou.yaku_id, 13),
            (DaiSuushii.yaku_id, 26),
        ]
        assert result.pao_seat == 3
        assert result.hand_result.points == 96000
        assert result.score_changes == {0: 0, 1: 96300, 2: -64000, 3: -32300}

    def test_pao__when_lowered_threshold_hand_wins_without_the_pao_yakuman__should_settle_as_ordinary_ron(self):
        settings = GameSettings(daisangen_pao_set_threshold=2)
        closed_tiles = [*tile_copies(0, pin="234678"), *TilesConverter.string_to_136_array(honors="7")]
        melds = _honor_pons(1, from_seat=3, honors="56")
        winner = create_player(seat=1, tiles=closed_tiles, melds=melds, pao_seat=3)
        chun_win_tile = tile_copies(1, honors="7")[0]
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=2,
            discarded_tile=chun_win_tile,
            settings=settings,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=chun_win_tile, discarder_seat=2),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.pao_seat is None
        assert result.hand_result.points == 12000
        assert result.score_changes == {0: 0, 1: 12000, 2: -12000, 3: 0}

    def test_pao__when_double_ron_with_honba__should_charge_the_pao_winners_honba_to_the_pao_player(self):
        pao_winner = _daisangen_tanki_player(0, pao_seat=2)
        other_winner = create_player(seat=1, tiles=_ITTSUU_SHANPON_HAND)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[pao_winner, other_winner],
            current_seat=3,
            discarded_tile=_DAISANGEN_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[0, 1], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=3),
        )
        result = _round_result(events)
        assert isinstance(result, DoubleRonResult)
        assert [w.pao_seat for w in result.winners] == [2, None]
        assert [w.hand_result.points for w in result.winners] == [48000, 5200]
        assert [w.score_changes for w in result.winners] == [
            {0: 48300, 1: 0, 2: -24300, 3: -24000},
            {0: 0, 1: 5500, 2: 0, 3: -5500},
        ]
        assert result.score_changes == {0: 48300, 1: 5500, 2: -24300, 3: -29500}

    def test_pao__when_double_ron_liable_player_is_the_other_winner__should_charge_them_half_the_yakuman(self):
        other_winner = create_player(seat=1, tiles=_ITTSUU_SHANPON_HAND)
        pao_winner = _daisangen_tanki_player(2, pao_seat=1)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[other_winner, pao_winner],
            current_seat=0,
            discarded_tile=_DAISANGEN_WIN_TILE,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1, 2], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=0),
        )
        result = _round_result(events)
        assert isinstance(result, DoubleRonResult)
        assert [w.pao_seat for w in result.winners] == [None, 1]
        assert [w.hand_result.points for w in result.winners] == [5200, 32000]
        assert [w.score_changes for w in result.winners] == [
            {0: -5200, 1: 5200, 2: 0, 3: 0},
            {0: -16000, 1: -16000, 2: 32000, 3: 0},
        ]
        assert result.score_changes == {0: -21200, 1: -10800, 2: 32000, 3: 0}


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
        assert [(y.yaku_id, y.han) for y in result.yaku] == [(1, 1), (4, 1), (27, 2), (120, 1), (121, 2), (122, 1)]
        assert result.han == 8

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
        win_tile = TilesConverter.string_to_136_array(man="55")[1]
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
        assert [(y.yaku_id, y.han) for y in result.yaku] == [(4, 1), (120, 1), (121, 2)]
        assert result.han == 4

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
        win_tile = tile_copies(1, man="5")[0]
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
        result_b = calculate_hand_value_with_tiles(ctx, tiles=tiles, win_tile=win_tile)
        assert result_a.han == result_b.han
        assert result_a.fu == result_b.fu
        assert result_a.cost_main == result_b.cost_main
        assert result_a.cost_additional == result_b.cost_additional
        assert result_a.yaku == result_b.yaku
        assert result_a.error == result_b.error

    def test_calculate_hand_value_with_tiles__when_no_yaku__should_match_calculate_hand_value_error(self):
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        win_tile = tile_copies(1, man="5")
        hand_after_draw = (*closed_tiles, *win_tile)

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=hand_after_draw, melds=(pon,))
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result_a = calculate_hand_value(ctx, win_tile[0])
        result_b = calculate_hand_value_with_tiles(ctx, tiles=[*hand_after_draw, *pon_tiles], win_tile=win_tile[0])
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

        new_game_state, _result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        assert new_game_state.riichi_sticks == 3


class TestUraDoraScoringIntegration:
    def _build_game_state(self, *, dead_wall, dora_indicators, tiles, is_riichi):
        nine_pin_closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, pin="9999")), opened=False, who=1, from_who=1
        )
        riichi_discard = Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True)
        players = (
            create_player(seat=0, tiles=tuple(tiles), is_riichi=is_riichi, discards=(riichi_discard,)),
            create_player(
                seat=1,
                tiles=(*tile_copies(1, pin="12345678"), *tile_copies(0, honors="55")),
                melds=(nine_pin_closed_kan,),
                discards=(Discard(tile_id=tile_copies(1, honors="7")[0]),),
            ),
            create_player(seat=2, tiles=(*tile_copies(2, pin="12345678"), *tile_copies(0, honors="66234"))),
            create_player(seat=3, tiles=(*tile_copies(3, pin="12345678"), *tile_copies(2, honors="56234"))),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            dora_indicators=dora_indicators,
            dead_wall=dead_wall,
            wall=tile_copies(2, man="123456789"),
            all_discards=tuple(d.tile_id for p in players for d in p.discards),
        )
        return create_game_state(round_state=round_state)

    def test_calculate_hand_value__when_riichi_after_kan__should_count_ura_dora_for_each_indicator(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        dora_indicator_1 = tile_copies(1, man="1")[0]
        dora_indicator_2 = tile_copies(1, man="5")[0]

        # ura dora 1: indicator 4s -> ura dora 5s (2 copies in hand = 2 han)
        # ura dora 2: indicator 1s -> ura dora 2s (1 copy in hand = 1 han)
        ura_tile_1 = tile_copies(1, sou="4")[0]
        ura_tile_2 = tile_copies(1, sou="1")[0]

        dead_wall: list[int | None] = [None] * 14
        dead_wall[2] = dora_indicator_1
        dead_wall[3] = dora_indicator_2
        dead_wall[FIRST_URA_POSITION] = ura_tile_1
        dead_wall[FIRST_URA_POSITION + 1] = ura_tile_2

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
