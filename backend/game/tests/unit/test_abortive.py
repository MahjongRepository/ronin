import pytest
from mahjong.tile import TilesConverter

from game.logic.abortive import (
    AbortiveDrawType,
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
    check_four_riichi,
    check_four_winds,
)
from game.logic.enums import RoundResultType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import GameSettings
from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.tests.helpers.wall import make_wall

_PIN_5S = tuple(TilesConverter.string_to_136_array(pin="5555"))


class TestCanCallKyuushuKyuuhai:
    def _create_round_state(
        self,
        tiles: list[int],
        *,
        player_discards: tuple[Discard, ...] | None = None,
    ) -> MahjongRoundState:
        players = (
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=tuple(tiles),
                discards=player_discards or (),
                score=25000,
            ),
            MahjongPlayer(seat=1, name="AI1", tiles=(), score=25000),
            MahjongPlayer(seat=2, name="AI2", tiles=(), score=25000),
            MahjongPlayer(seat=3, name="AI3", tiles=(), score=25000),
        )
        return MahjongRoundState(
            wall=make_wall(),
            players=players,
            current_player_seat=0,
        )

    def _create_kyuushu_hand(self) -> list[int]:
        # 9 different types: 1m, 9m, 1p, 9p, 1s, 9s, E, S, W + 5 middle tiles
        # 14 tiles (just drew)
        return [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123"),
            # filler tiles (middle tiles, not terminal/honor)
            *TilesConverter.string_to_136_array(man="22334"),
        ]

    def _create_non_kyuushu_hand(self) -> list[int]:
        # 8 different types: 1m, 9m, 1p, 9p, 1s, 9s, E, S + 6 middle tiles
        return [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="12"),
            # filler tiles (middle tiles, not terminal/honor)
            *TilesConverter.string_to_136_array(man="223345"),
        ]

    def test_can_call_kyuushu_kyuuhai__when_9_terminal_honor_types__should_allow(self):
        tiles = self._create_kyuushu_hand()
        round_state = self._create_round_state(tiles)
        settings = GameSettings()

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state, settings=settings)
        assert result is True

    def test_can_call_kyuushu_kyuuhai__when_8_terminal_honor_types__should_forbid(self):
        tiles = self._create_non_kyuushu_hand()
        round_state = self._create_round_state(tiles)
        settings = GameSettings()

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state, settings=settings)
        assert result is False

    def test_can_call_kyuushu_kyuuhai__when_disabled_by_settings__should_forbid(self):
        tiles = self._create_kyuushu_hand()
        round_state = self._create_round_state(tiles)
        settings = GameSettings(has_kyuushu_kyuuhai=False)

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state, settings=settings)
        assert result is False

    def test_can_call_kyuushu_kyuuhai__when_non_dealer_first_draw_after_others_discarded__should_allow(self):
        pin_4a, pin_4b = TilesConverter.string_to_136_array(pin="44")
        dealer = MahjongPlayer(seat=0, name="Dealer", discards=(Discard(tile_id=pin_4a),), score=25000)
        shimocha = MahjongPlayer(seat=1, name="Shimocha", discards=(Discard(tile_id=pin_4b),), score=25000)
        toimen_on_first_draw = MahjongPlayer(
            seat=2, name="Toimen", tiles=tuple(self._create_kyuushu_hand()), score=25000
        )
        kamicha = MahjongPlayer(seat=3, name="Kamicha", score=25000)
        round_state = MahjongRoundState(
            wall=make_wall(),
            players=(dealer, shimocha, toimen_on_first_draw, kamicha),
            dealer_seat=0,
            current_player_seat=2,
        )

        result = can_call_kyuushu_kyuuhai(toimen_on_first_draw, round_state, settings=GameSettings())
        assert result is True

    def test_can_call_kyuushu_kyuuhai__when_player_discarded__should_forbid(self):
        tiles = self._create_kyuushu_hand()
        discard = Discard(tile_id=TilesConverter.string_to_136_array(pin="444")[2])
        round_state = self._create_round_state(tiles, player_discards=(discard,))
        settings = GameSettings()

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state, settings=settings)
        assert result is False

    def test_can_call_kyuushu_kyuuhai__when_meld_exists__should_forbid(self):
        tiles = self._create_kyuushu_hand()
        pin_4s = tuple(TilesConverter.string_to_136_array(pin="444"))
        pon = FrozenMeld(meld_type=FrozenMeld.PON, tiles=pin_4s, opened=True, called_tile=pin_4s[0], who=2, from_who=1)
        round_state = self._create_round_state(tiles)
        players = list(round_state.players)
        players[2] = players[2].model_copy(update={"melds": (pon,)})
        round_state = round_state.model_copy(update={"players": tuple(players)})
        settings = GameSettings()

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state, settings=settings)
        assert result is False

    def test_can_call_kyuushu_kyuuhai__when_closed_kan_exists__should_forbid(self):
        tiles = self._create_kyuushu_hand()
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(pin="1111")),
            opened=False,
        )
        players = (
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=tuple(tiles),
                score=25000,
            ),
            MahjongPlayer(
                seat=1,
                name="AI1",
                tiles=(),
                melds=(closed_kan,),
                score=25000,
            ),
            MahjongPlayer(seat=2, name="AI2", tiles=(), score=25000),
            MahjongPlayer(seat=3, name="AI3", tiles=(), score=25000),
        )
        round_state = MahjongRoundState(
            wall=make_wall(),
            players=players,
            current_player_seat=0,
        )
        settings = GameSettings()

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state, settings=settings)
        assert result is False

    def test_can_call_kyuushu_kyuuhai__when_duplicate_terminals__should_count_each_type_once(self):
        # 9 types but with duplicates: 1m 1m 1m 9m 1p 9p 1s 9s E S W (8 unique types)
        tiles = [
            *TilesConverter.string_to_136_array(man="111")[0:3],  # 1m x3
            *TilesConverter.string_to_136_array(man="9", pin="19", sou="19", honors="12"),
            # filler middle tiles
            *TilesConverter.string_to_136_array(man="2233"),
        ]
        round_state = self._create_round_state(tiles)
        settings = GameSettings()

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state, settings=settings)
        # only 8 unique types, not enough
        assert result is False


class TestCallKyuushuKyuuhai:
    def _create_round_state(self, current_player_seat: int = 0) -> MahjongRoundState:
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="AI1", score=25000),
            MahjongPlayer(seat=2, name="AI2", score=25000),
            MahjongPlayer(seat=3, name="AI3", score=25000),
        ]
        return MahjongRoundState(
            wall=make_wall(),
            players=players,
            current_player_seat=current_player_seat,
        )

    def test_call_kyuushu_kyuuhai__should_return_nine_terminals_abortive_draw(self):
        round_state = self._create_round_state()

        _new_round_state, result = call_kyuushu_kyuuhai(round_state)
        assert result.type == RoundResultType.ABORTIVE_DRAW
        assert result.reason == AbortiveDrawType.NINE_TERMINALS

    def test_call_kyuushu_kyuuhai__should_record_calling_seat(self):
        round_state = self._create_round_state(current_player_seat=2)

        _new_round_state, result = call_kyuushu_kyuuhai(round_state)
        assert result.seat == 2


class TestCheckFourRiichi:
    def _create_round_state(
        self,
        riichi_seats: tuple[int, ...] = (),
    ) -> MahjongRoundState:
        players = [
            MahjongPlayer(seat=0, name="Player1", is_riichi=(0 in riichi_seats), score=25000),
            MahjongPlayer(seat=1, name="AI1", is_riichi=(1 in riichi_seats), score=25000),
            MahjongPlayer(seat=2, name="AI2", is_riichi=(2 in riichi_seats), score=25000),
            MahjongPlayer(seat=3, name="AI3", is_riichi=(3 in riichi_seats), score=25000),
        ]
        return MahjongRoundState(wall=make_wall(), players=players)

    def test_check_four_riichi__when_four_players_in_riichi__should_abort(self):
        round_state = self._create_round_state(riichi_seats=(0, 1, 2, 3))

        result = check_four_riichi(round_state)
        assert result is True

    def test_check_four_riichi__when_three_players_in_riichi__should_not_abort(self):
        round_state = self._create_round_state(riichi_seats=(0, 1, 2))

        result = check_four_riichi(round_state)
        assert result is False


class TestCheckFourWinds:
    def _create_round_state(
        self,
        all_discards: tuple[int, ...] = (),
        player1_melds: tuple[FrozenMeld, ...] = (),
    ) -> MahjongRoundState:
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="AI1", melds=player1_melds, score=25000),
            MahjongPlayer(seat=2, name="AI2", score=25000),
            MahjongPlayer(seat=3, name="AI3", score=25000),
        ]
        return MahjongRoundState(
            wall=make_wall(),
            players=players,
            all_discards=all_discards,
        )

    def test_check_four_winds__when_four_same_winds_discarded__should_abort(self):
        round_state = self._create_round_state(
            all_discards=tuple(TilesConverter.string_to_136_array(honors="1111")),
        )
        settings = GameSettings()

        result = check_four_winds(round_state, settings)
        assert result is True

    def test_check_four_winds__when_mixed_winds__should_not_abort(self):
        # E, S, W, N
        round_state = self._create_round_state(
            all_discards=tuple(TilesConverter.string_to_136_array(honors="1234")),
        )
        settings = GameSettings()

        result = check_four_winds(round_state, settings)
        assert result is False

    def test_check_four_winds__when_non_wind_tiles__should_not_abort(self):
        # 1m tiles
        round_state = self._create_round_state(
            all_discards=tuple(TilesConverter.string_to_136_array(man="1111")),
        )
        settings = GameSettings()

        result = check_four_winds(round_state, settings)
        assert result is False

    def test_check_four_winds__when_four_dragons__should_not_abort(self):
        round_state = self._create_round_state(
            all_discards=tuple(TilesConverter.string_to_136_array(honors="5555")),
        )
        settings = GameSettings()

        result = check_four_winds(round_state, settings)
        assert result is False

    def test_check_four_winds__when_fewer_than_4_discards__should_not_abort(self):
        round_state = self._create_round_state(
            all_discards=tuple(TilesConverter.string_to_136_array(honors="111")[:3]),
        )
        settings = GameSettings()

        result = check_four_winds(round_state, settings)
        assert result is False

    def test_check_four_winds__when_more_than_4_discards__should_not_abort(self):
        round_state = self._create_round_state(
            all_discards=(
                *TilesConverter.string_to_136_array(honors="1111"),
                TilesConverter.string_to_136_array(honors="22")[0],
            ),
        )
        settings = GameSettings()

        result = check_four_winds(round_state, settings)
        assert result is False

    @pytest.mark.parametrize(
        ("meld", "expected_abort"),
        [
            (FrozenMeld(meld_type=FrozenMeld.PON, tiles=_PIN_5S[:3], opened=True, who=1, from_who=0), False),
            (FrozenMeld(meld_type=FrozenMeld.KAN, tiles=_PIN_5S, opened=False, who=1, from_who=1), True),
        ],
        ids=["open_pon_blocks", "closed_kan_does_not_block"],
    )
    def test_check_four_winds__when_a_player_has_a_meld__should_abort_only_without_open_melds(
        self, meld, expected_abort
    ):
        round_state = self._create_round_state(
            all_discards=tuple(TilesConverter.string_to_136_array(honors="1111")),
            player1_melds=(meld,),
        )

        assert check_four_winds(round_state, GameSettings()) is expected_abort
