from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.riichi import declare_riichi
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.wall import Wall


class TestDeclareRiichiDaburi:
    def _create_tempai_hand(self) -> tuple[int, ...]:
        return tuple(TilesConverter.string_to_136_array(man="1123456788899"))

    def _create_game_state(
        self,
        *,
        player_discards: tuple[Discard, ...] | None = None,
        other_player_melds: dict[int, tuple[FrozenMeld, ...]] | None = None,
    ) -> tuple[MahjongRoundState, MahjongGameState]:
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=self._create_tempai_hand(),
            score=25000,
            discards=player_discards or (),
        )
        melds_map = other_player_melds or {}
        players = (
            player,
            *tuple(MahjongPlayer(seat=i, name=f"AI{i}", score=25000, melds=melds_map.get(i, ())) for i in range(1, 4)),
        )
        round_state = MahjongRoundState(
            wall=Wall(live_tiles=tuple(range(10))),
            players=players,
        )
        game_state = MahjongGameState(
            round_state=round_state,
        )
        return round_state, game_state

    def test_declare_riichi__when_riichi_discard_is_first_discard__should_set_daburi(self):
        round_state, game_state = self._create_game_state(
            player_discards=(Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),),
        )
        assert round_state.players[0].is_daburi is False

        settings = GameSettings()
        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=settings,
        )
        assert new_round_state.players[0].is_daburi is True
        # original state unchanged
        assert round_state.players[0].is_daburi is False

    def test_declare_riichi__when_player_already_discarded__should_not_set_daburi(self):
        round_state, game_state = self._create_game_state(
            player_discards=(
                Discard(tile_id=TilesConverter.string_to_136_array(sou="88")[0]),
                Discard(tile_id=TilesConverter.string_to_136_array(sou="88")[1], is_riichi_discard=True),
            ),
        )

        settings = GameSettings()
        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=settings,
        )
        assert new_round_state.players[0].is_daburi is False

    def test_declare_riichi__when_open_meld_exists__should_not_set_daburi(self):
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(pin="555")),
            opened=True,
            who=1,
            from_who=0,
        )
        round_state, game_state = self._create_game_state(
            player_discards=(Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),),
            other_player_melds={1: (pon,)},
        )

        settings = GameSettings()
        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=settings,
        )
        assert new_round_state.players[0].is_daburi is False

    def test_declare_riichi__when_other_player_has_closed_kan__should_not_set_daburi(self):
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(pin="1111")),
            opened=False,
        )
        round_state, game_state = self._create_game_state(
            player_discards=(Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),),
            other_player_melds={1: (closed_kan,)},
        )

        settings = GameSettings()
        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=settings,
        )
        assert new_round_state.players[0].is_daburi is False

    def test_declare_riichi__should_set_ippatsu_only_for_declarer(self):
        round_state, game_state = self._create_game_state(
            player_discards=(Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),),
        )
        assert round_state.players[0].is_ippatsu is False

        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=GameSettings(),
        )
        assert new_round_state.players[0].is_ippatsu is True
        # other players not affected
        for i in range(1, 4):
            assert new_round_state.players[i].is_ippatsu is False
