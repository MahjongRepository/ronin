"""Unit tests for get_player_view and meld_to_view."""

from mahjong.tile import TilesConverter

from game.logic.enums import MeldViewType, WindName
from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import (
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    get_player_view,
    meld_to_view,
)


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
                    )
                ),
                score=25000,
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
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
                name="Bot2",
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
                name="Bot3",
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
            wall=tuple(range(84, 122)),  # remaining wall tiles
            dead_wall=tuple(range(122, 136)),
            dora_indicators=(haku,),  # haku as dora indicator
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

    def test_view_contains_basic_info(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        assert view.seat == 0
        assert view.round_wind == WindName.EAST
        assert view.round_number == 0
        assert view.dealer_seat == 0
        assert view.current_player_seat == 0
        assert view.honba_sticks == 0
        assert view.riichi_sticks == 0

    def test_view_contains_dora_indicators(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        haku = TilesConverter.string_to_136_array(honors="5")[0]
        assert len(view.dora_indicators) == 1
        assert view.dora_indicators[0] == haku

    def test_view_contains_my_tiles(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        assert len(view.my_tiles) == 13

    def test_view_shows_all_player_scores(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        assert view.players[0].score == 25000
        assert view.players[1].score == 24000
        assert view.players[2].score == 26000
        assert view.players[3].score == 25000

    def test_view_for_different_seats(self):
        game_state = self._create_test_game_state()

        view0 = get_player_view(game_state, seat=0)
        view1 = get_player_view(game_state, seat=1)

        assert view0.my_tiles != view1.my_tiles
        assert len(view0.my_tiles) == 13
        assert len(view1.my_tiles) == 13


class TestMeldToView:
    def test_open_kan(self):
        """Open kan maps to OPEN_KAN view type."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1111"))
        meld = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tiles, opened=True, from_who=1)
        view = meld_to_view(meld)
        assert view.type == MeldViewType.OPEN_KAN
        assert view.opened is True

    def test_closed_kan(self):
        """Closed kan maps to CLOSED_KAN view type."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1111"))
        meld = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tiles, opened=False)
        view = meld_to_view(meld)
        assert view.type == MeldViewType.CLOSED_KAN
        assert view.opened is False

    def test_chankan(self):
        """Chankan maps to ADDED_KAN view type."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1111"))
        meld = FrozenMeld(meld_type=FrozenMeld.CHANKAN, tiles=tiles, opened=True, from_who=1)
        view = meld_to_view(meld)
        assert view.type == MeldViewType.ADDED_KAN

    def test_shouminkan(self):
        """Shouminkan maps to ADDED_KAN view type."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1111"))
        meld = FrozenMeld(meld_type=FrozenMeld.SHOUMINKAN, tiles=tiles, opened=True, from_who=1)
        view = meld_to_view(meld)
        assert view.type == MeldViewType.ADDED_KAN

    def test_unknown_type(self):
        """Unrecognized meld type maps to UNKNOWN view type."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1111"))
        meld = FrozenMeld(meld_type="invalid_type", tiles=tiles, opened=False)
        view = meld_to_view(meld)
        assert view.type == MeldViewType.UNKNOWN
