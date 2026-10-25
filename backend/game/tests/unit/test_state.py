from mahjong.tile import TilesConverter

from game.logic.enums import WindName
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import (
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    get_player_view,
)
from game.logic.state_utils import finish_round
from game.logic.types import DoubleRonResult, DoubleRonWinner, HandResultInfo, YakuInfo
from game.tests.helpers.wall import make_wall


class TestGetPlayerView:
    def _create_test_game_state(self):
        haku = TilesConverter.string_to_136_array(honors="5")[0]
        players = (
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=tuple(
                    TilesConverter.string_to_136_array(
                        man="123",
                        pin="123",
                        sou="123",
                        honors="1115",
                    ),
                ),
                score=25000,
            ),
            MahjongPlayer(
                seat=1,
                name="AI1",
                tiles=(
                    *TilesConverter.string_to_136_array(man="112233")[1::2],
                    *TilesConverter.string_to_136_array(pin="112233")[1::2],
                    *TilesConverter.string_to_136_array(sou="112233")[1::2],
                    *TilesConverter.string_to_136_array(honors="222"),
                    TilesConverter.string_to_136_array(honors="55")[1],
                ),
                score=24000,
            ),
            MahjongPlayer(
                seat=2,
                name="AI2",
                tiles=(
                    *TilesConverter.string_to_136_array(man="111222333")[2::3],
                    *TilesConverter.string_to_136_array(pin="111222333")[2::3],
                    *TilesConverter.string_to_136_array(sou="111222333")[2::3],
                    *TilesConverter.string_to_136_array(honors="333"),
                    TilesConverter.string_to_136_array(honors="555")[2],
                ),
                score=26000,
            ),
            MahjongPlayer(
                seat=3,
                name="AI3",
                tiles=(
                    *TilesConverter.string_to_136_array(man="111122223333")[3::4],
                    *TilesConverter.string_to_136_array(pin="111122223333")[3::4],
                    *TilesConverter.string_to_136_array(sou="111122223333")[3::4],
                    *TilesConverter.string_to_136_array(honors="444"),
                    TilesConverter.string_to_136_array(honors="5555")[3],
                ),
                score=25000,
            ),
        )

        round_state = MahjongRoundState(
            wall=make_wall(
                live_tiles=tuple(range(84, 122)),
                dead_wall=tuple(range(122, 136)),
                dora_indicators=(haku,),
            ),
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,  # east
        )

        return MahjongGameState(
            round_state=round_state,
            round_number=0,
            honba_sticks=0,
            riichi_sticks=0,
        )

    def test_get_player_view__when_round_wind_is_int__should_convert_to_wind_name(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        # round_wind=0 (int) should be converted to WindName.EAST
        assert view.round_wind == WindName.EAST

    def test_get_player_view__when_different_seats__should_show_each_seats_own_tiles(self):
        game_state = self._create_test_game_state()

        view0 = get_player_view(game_state, seat=0)
        view1 = get_player_view(game_state, seat=1)
        assert view0.my_tiles != view1.my_tiles
        assert len(view0.my_tiles) == 13
        assert len(view1.my_tiles) == 13


class TestFinishRound:
    def test_finish_round__when_double_ron__should_record_both_winners_and_the_loser_in_round_history(self):
        game_state = MahjongGameService().start_game("game1", ["Alice"], seed="a" * 192).runtime.state
        winners = [
            DoubleRonWinner(
                winner_seat=seat,
                hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000),
                score_changes={2: -1000, seat: 1000},
                riichi_sticks_collected=0,
                closed_tiles=[],
                melds=[],
            )
            for seat in (3, 0)
        ]
        result = DoubleRonResult(
            loser_seat=2,
            winning_tile=42,
            winners=winners,
            scores={0: 26000, 1: 25000, 2: 23000, 3: 26000},
            score_changes={0: 1000, 1: 0, 2: -2000, 3: 1000},
        )

        new_game_state, _ = finish_round(game_state, result)
        entry = new_game_state.round_history[-1]
        assert len(new_game_state.round_history) == 1
        assert (entry.winner_seats, entry.loser_seat, entry.tenpai_seats) == ((3, 0), 2, None)
