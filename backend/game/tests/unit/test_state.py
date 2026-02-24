"""Unit tests for get_player_view."""

from mahjong.tile import TilesConverter

from game.logic.enums import WindName
from game.logic.state import (
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    get_player_view,
)
from game.logic.wall import Wall


class TestGetPlayerView:
    def _create_test_game_state(self):
        """Create a game state for testing."""
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
            wall=Wall(
                live_tiles=tuple(range(84, 122)),
                dead_wall_tiles=tuple(range(122, 136)),
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

    def test_view_converts_round_wind_to_name(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        # round_wind=0 (int) should be converted to WindName.EAST
        assert view.round_wind == WindName.EAST

    def test_view_for_different_seats(self):
        game_state = self._create_test_game_state()

        view0 = get_player_view(game_state, seat=0)
        view1 = get_player_view(game_state, seat=1)

        assert view0.my_tiles != view1.my_tiles
        assert len(view0.my_tiles) == 13
        assert len(view1.my_tiles) == 13
