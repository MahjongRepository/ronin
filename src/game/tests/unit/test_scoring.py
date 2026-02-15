"""
Unit tests for scoring calculation.
"""

from mahjong.tile import TilesConverter

from game.logic.enums import MeldViewType, RoundResultType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import (
    HandResult,
    _collect_dora_indicators,
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
from game.logic.wall import Wall
from game.tests.conftest import create_game_state, create_player, create_round_state


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    """Create stub YakuInfo list for scoring tests where yaku content is not asserted."""
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


def _create_scoring_game_state(dealer_seat: int = 0, round_wind: int = 0) -> MahjongGameState:
    """
    Create a game state with 4 players for scoring tests.

    Set up a mid-game state (some discards, non-empty wall) to avoid
    triggering Tenhou/Chiihou.
    """
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
    def test_dealer_is_east(self):
        assert seat_to_wind(0, 0) == EAST_34

    def test_dealer_plus_one_is_south(self):
        assert seat_to_wind(1, 0) == SOUTH_34

    def test_dealer_plus_two_is_west(self):
        assert seat_to_wind(2, 0) == WEST_34

    def test_dealer_plus_three_is_north(self):
        assert seat_to_wind(3, 0) == NORTH_34

    def test_dealer_at_seat_2(self):
        # dealer at seat 2
        # seat 2 = East, seat 3 = South, seat 0 = West, seat 1 = North
        assert seat_to_wind(2, 2) == EAST_34
        assert seat_to_wind(3, 2) == SOUTH_34
        assert seat_to_wind(0, 2) == WEST_34
        assert seat_to_wind(1, 2) == NORTH_34


class TestCalculateHandValue:
    def test_menzen_tsumo_hand(self):
        # 123m 456m 789m 123p 55p - pinfu tsumo
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles))
        player = round_state.players[0]

        win_tile = tiles[-1]  # 5p
        settings = GameSettings()
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=True)

        assert result.error is None
        assert result.han >= 1  # at least menzen tsumo
        assert result.fu > 0
        assert result.cost_main > 0
        assert len(result.yaku) > 0

    def test_riichi_hand(self):
        # closed hand with riichi
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=True)

        assert result.error is None
        assert result.han >= 2  # riichi + menzen tsumo
        assert any(y.yaku_id == 1 for y in result.yaku)  # Riichi

    def test_ippatsu_hand(self):
        # riichi with ippatsu
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(
            game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True, is_ippatsu=True
        )
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=True)

        assert result.error is None
        assert result.han >= 3  # riichi + ippatsu + menzen tsumo
        assert any(y.yaku_id == 3 for y in result.yaku)  # Ippatsu

    def test_ron_hand(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=False)

        assert result.error is None
        assert result.han >= 1  # riichi
        assert not any(y.yaku_id == 0 for y in result.yaku)  # no Menzen Tsumo

    def test_haitei_tsumo(self):
        # last tile draw (haitei)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles))
        round_state = round_state.model_copy(update={"wall": Wall()})  # empty wall = last tile
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=True)

        assert result.error is None
        assert any(y.yaku_id == 6 for y in result.yaku)  # Haitei Raoyue

    def test_houtei_ron(self):
        # last discard ron (houtei)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        round_state = round_state.model_copy(update={"wall": Wall()})  # empty wall = last discard possible
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=False)

        assert result.error is None
        assert any(y.yaku_id == 7 for y in result.yaku)  # Houtei Raoyui

    def test_no_yaku_error(self):
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
        result = calculate_hand_value(player, round_state, win_tile[0], settings, is_tsumo=True)

        assert result.error == "no_yaku"

    def test_ron_open_hand_meld_tiles_removed_from_hand(self):
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
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=False)

        assert result.error is None
        assert result.han >= 1  # yakuhai (haku)
        assert result.cost_main > 0

    def test_tsumo_open_hand_meld_tiles_removed_from_hand(self):
        # after meld call in actual gameplay, meld tiles are removed from player.tiles
        # closed: 234m 567m 234s 55s (11 tiles) + PON(Haku) (meld) = 14 total (drawn 4s)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
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
        round_state = update_player(game_state.round_state, 0, tiles=tuple(closed_tiles), melds=(pon,))
        player = round_state.players[0]

        win_tile = closed_tiles[-1]  # last tile drawn (5s)
        settings = GameSettings()
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=True)

        assert result.error is None
        assert result.han >= 1  # yakuhai (haku)
        assert result.cost_main > 0


class TestApplyTsumoScore:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_dealer_tsumo_basic(self):
        # dealer wins with 30fu 2han = 2000 all (dealer tsumo)
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        # dealer (seat 0) gets 6000 total (2000 * 3)
        assert new_round_state.players[0].score == 25000 + 6000
        # each non-dealer pays 2000
        assert new_round_state.players[1].score == 25000 - 2000
        assert new_round_state.players[2].score == 25000 - 2000
        assert new_round_state.players[3].score == 25000 - 2000

    def test_tsumo_with_honba(self):
        # tsumo with 2 honba sticks = +200 total (100 per loser)
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state, winner_seat=1, hand_result=hand_result
        )

        # winner gets 2000 + 600 (300 * 2 honba, but per-loser so 100*2*3=600)
        assert new_round_state.players[1].score == 25000 + 2600
        # dealer pays 1000 + 200
        assert new_round_state.players[0].score == 25000 - 1200
        # non-dealers pay 500 + 200
        assert new_round_state.players[2].score == 25000 - 700
        assert new_round_state.players[3].score == 25000 - 700

    def test_tsumo_with_riichi_sticks(self):
        # tsumo with 2 riichi sticks on table
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_round_state, new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=1, hand_result=hand_result
        )

        # winner gets 2000 + 2000 (riichi sticks)
        assert new_round_state.players[1].score == 25000 + 4000
        # riichi sticks should be cleared
        assert new_game_state.riichi_sticks == 0
        assert result.riichi_sticks_collected == 2

    def test_tsumo_non_riichi_ura_dora_is_none(self):
        """Non-riichi tsumo winner has ura_dora_indicators=None."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        assert result.ura_dora_indicators is None

    def test_tsumo_riichi_winner_has_ura_dora_indicators(self):
        """Riichi tsumo winner gets ura dora indicators from dead wall."""
        dead_wall = tuple(range(100, 114))
        dora_indicators = (dead_wall[2],)
        players = tuple(
            create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], is_riichi=(i == 0)) for i in range(4)
        )
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
            game_state, winner_seat=0, hand_result=hand_result
        )

        assert result.ura_dora_indicators == [dead_wall[7]]

    def test_tsumo_result_carries_closed_tiles(self):
        """TsumoResult includes winner's closed tiles."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        assert result.closed_tiles == [0, 1, 2, 3]

    def test_tsumo_result_carries_win_tile(self):
        """TsumoResult win_tile is the last tile in the winner's hand."""
        players = tuple(create_player(seat=i, score=25000, tiles=[50, 60, 70, 80]) for i in range(4))
        round_state = create_round_state(players=players, dealer_seat=0, current_player_seat=0, round_wind=0)
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        assert result.win_tile == 80

    def test_tsumo_result_carries_empty_melds(self):
        """TsumoResult melds is empty when winner has no melds."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        assert result.melds == []

    def test_tsumo_result_carries_melds(self):
        """TsumoResult includes winner's melds when present."""
        pon_tiles = (10, 11, 12)
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=10,
            who=0,
            from_who=1,
        )
        players = tuple(
            create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], melds=(pon,) if i == 0 else ())
            for i in range(4)
        )
        round_state = create_round_state(players=players, dealer_seat=0, current_player_seat=0, round_wind=0)
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        assert len(result.melds) == 1
        assert result.melds[0].type == MeldViewType.PON
        assert result.melds[0].tile_ids == [10, 11, 12]


class TestApplyRonScore:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_ron_with_honba(self):
        # ron with 3 honba sticks = +900 total
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 3})
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        # winner gets 2000 + 900
        assert new_round_state.players[0].score == 25000 + 2900
        # loser pays 2000 + 900
        assert new_round_state.players[1].score == 25000 - 2900

    def test_ron_with_riichi_sticks(self):
        # ron with 3 riichi sticks
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 3})
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_round_state, new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        # winner gets 2000 + 3000
        assert new_round_state.players[0].score == 25000 + 5000
        # loser only pays 2000
        assert new_round_state.players[1].score == 25000 - 2000
        # riichi sticks cleared
        assert new_game_state.riichi_sticks == 0
        assert result.riichi_sticks_collected == 3

    def test_ron_non_riichi_ura_dora_is_none(self):
        """Non-riichi ron winner has ura_dora_indicators=None."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        assert result.ura_dora_indicators is None

    def test_ron_riichi_winner_has_ura_dora_indicators(self):
        """Riichi ron winner gets ura dora indicators from dead wall."""
        dead_wall = tuple(range(100, 114))
        dora_indicators = (dead_wall[2],)
        players = tuple(
            create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], is_riichi=(i == 0)) for i in range(4)
        )
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
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        assert result.ura_dora_indicators == [dead_wall[7]]

    def test_ron_result_carries_closed_tiles_and_winning_tile(self):
        """RonResult includes winner's closed tiles and the winning tile."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=42
        )

        assert result.closed_tiles == [0, 1, 2, 3]
        assert result.winning_tile == 42

    def test_ron_result_carries_empty_melds(self):
        """RonResult melds is empty when winner has no melds."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        assert result.melds == []

    def test_ron_result_carries_melds(self):
        """RonResult includes winner's melds when present."""
        pon_tiles = (10, 11, 12)
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=10,
            who=0,
            from_who=1,
        )
        players = tuple(
            create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], melds=(pon,) if i == 0 else ())
            for i in range(4)
        )
        round_state = create_round_state(players=players, dealer_seat=0, current_player_seat=0, round_wind=0)
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        assert len(result.melds) == 1
        assert result.melds[0].type == MeldViewType.PON
        assert result.melds[0].tile_ids == [10, 11, 12]


class TestApplyDoubleRonScore:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_double_ron_basic(self):
        # two winners ron off one discard
        game_state = self._create_game_state()
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, _new_game_state, result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=1, winning_tile=55
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

    def test_double_ron_with_honba(self):
        # both winners get honba bonus
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"honba_sticks": 2})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, _new_game_state, _result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=1, winning_tile=0
        )

        # each winner gets 2000 + 600 honba
        assert new_round_state.players[0].score == 25000 + 2600
        assert new_round_state.players[2].score == 25000 + 2600
        # loser pays both (2000+600)*2 = 5200
        assert new_round_state.players[1].score == 25000 - 5200

    def test_double_ron_riichi_sticks_to_closest(self):
        # riichi sticks go to winner closest to loser's right (counter-clockwise)
        # loser is seat 1, checking seats 2, 3, 0 in order
        # if winners are 0 and 2, seat 2 is checked first
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 2})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, new_game_state, result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=1, winning_tile=0
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

    def test_double_ron_riichi_sticks_other_order(self):
        # different loser seat changes who gets riichi
        # loser is seat 3, checking seats 0, 1, 2 in order
        # if winners are 0 and 2, seat 0 is checked first
        game_state = self._create_game_state()
        game_state = game_state.model_copy(update={"riichi_sticks": 1})
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        new_round_state, _new_game_state, _result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=3, winning_tile=0
        )

        # seat 0 is closer (loser_seat + 1 = seat 0)
        # seat 0 gets 2000 + 1000 riichi
        assert new_round_state.players[0].score == 25000 + 3000
        # seat 2 only gets 2000
        assert new_round_state.players[2].score == 25000 + 2000

    def test_double_ron_non_riichi_ura_dora_is_none(self):
        """Non-riichi double ron winners have ura_dora_indicators=None."""
        game_state = self._create_game_state()
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        _new_round_state, _new_game_state, result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=1, winning_tile=0
        )

        for w in result.winners:
            assert w.ura_dora_indicators is None

    def test_double_ron_mixed_riichi_ura_dora(self):
        """In double ron, only riichi winner gets ura dora indicators."""
        dead_wall = tuple(range(100, 114))
        dora_indicators = (dead_wall[2],)
        # seat 0 is riichi, seat 2 is not
        players = tuple(
            create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], is_riichi=(i == 0)) for i in range(4)
        )
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
            game_state, winners=winners, loser_seat=1, winning_tile=0
        )

        for w in result.winners:
            if w.winner_seat == 0:
                assert w.ura_dora_indicators == [dead_wall[7]]
            else:
                assert w.ura_dora_indicators is None

    def test_double_ron_winners_carry_closed_tiles(self):
        """Each DoubleRonWinner includes its winner's closed tiles."""
        # give different tiles to seats 0 and 2
        players = tuple(
            create_player(seat=i, score=25000, tiles=[i * 10, i * 10 + 1, i * 10 + 2, i * 10 + 3])
            for i in range(4)
        )
        round_state = create_round_state(players=players, dealer_seat=0, current_player_seat=0, round_wind=0)
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        _new_round_state, _new_game_state, result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=1, winning_tile=0
        )

        for w in result.winners:
            if w.winner_seat == 0:
                assert w.closed_tiles == [0, 1, 2, 3]
            else:
                assert w.closed_tiles == [20, 21, 22, 23]

    def test_double_ron_winners_carry_melds(self):
        """Each DoubleRonWinner includes its winner's melds."""
        pon_tiles = (10, 11, 12)
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=10,
            who=2,
            from_who=1,
        )
        players = tuple(
            create_player(seat=i, score=25000, tiles=[0, 1, 2, 3], melds=(pon,) if i == 2 else ())
            for i in range(4)
        )
        round_state = create_round_state(players=players, dealer_seat=0, current_player_seat=0, round_wind=0)
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=3, fu=30, cost_main=4000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        _new_round_state, _new_game_state, result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=1, winning_tile=0
        )

        for w in result.winners:
            if w.winner_seat == 0:
                assert w.melds == []
            else:
                assert len(w.melds) == 1
                assert w.melds[0].type == MeldViewType.PON


class TestApplyNagashiManganScore:
    def _create_game_state(self, dealer_seat: int = 0) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
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

    def test_dealer_nagashi_mangan(self):
        """Dealer nagashi mangan: 4000 from each non-dealer."""
        game_state = self._create_game_state(dealer_seat=0)

        new_round_state, _new_game_state, result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0], tempai_seats=[], noten_seats=[0, 1, 2, 3], tenpai_hands=[]
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

    def test_non_dealer_nagashi_mangan(self):
        """Non-dealer nagashi mangan: 4000 from dealer + 2000 from each non-dealer."""
        game_state = self._create_game_state(dealer_seat=0)

        new_round_state, _new_game_state, result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[1], tempai_seats=[], noten_seats=[0, 1, 2, 3], tenpai_hands=[]
        )

        assert result.score_changes[1] == 8000
        assert result.score_changes[0] == -4000  # dealer pays 4000
        assert result.score_changes[2] == -2000  # non-dealer pays 2000
        assert result.score_changes[3] == -2000  # non-dealer pays 2000
        assert new_round_state.players[1].score == 33000
        assert new_round_state.players[0].score == 21000
        assert new_round_state.players[2].score == 23000
        assert new_round_state.players[3].score == 23000

    def test_multiple_qualifying_players(self):
        """Multiple players qualifying: each receives independent mangan payment."""
        game_state = self._create_game_state(dealer_seat=0)

        _new_round_state, _new_game_state, result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0, 2], tempai_seats=[], noten_seats=[0, 1, 2, 3], tenpai_hands=[]
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

    def test_tempai_and_noten_passed_through(self):
        """Tempai/noten seats are passed through to the result."""
        game_state = self._create_game_state(dealer_seat=0)

        _new_round_state, _new_game_state, result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0], tempai_seats=[1], noten_seats=[0, 2, 3], tenpai_hands=[]
        )

        assert result.tempai_seats == [1]
        assert result.noten_seats == [0, 2, 3]


class TestPaoTsumoScoring:
    """Tests for pao (liability) in tsumo wins."""

    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_pao_tsumo_non_dealer_yakuman(self):
        """Pao tsumo: liable player pays the full amount, others pay nothing."""
        game_state = self._create_game_state()
        # seat 1 wins with pao on seat 2
        # yakuman tsumo: dealer pays 16000, non-dealer pays 8000 each
        round_state = update_player(game_state.round_state, 1, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=1, hand_result=hand_result
        )

        # total would be: 16000 (from dealer) + 8000 + 8000 = 32000
        # pao player (seat 2) pays all 32000
        assert result.pao_seat == 2
        assert new_round_state.players[0].score == 25000  # dealer pays nothing
        assert new_round_state.players[1].score == 25000 + 32000  # winner gets all
        assert new_round_state.players[2].score == 25000 - 32000  # pao pays all
        assert new_round_state.players[3].score == 25000  # other pays nothing

    def test_pao_tsumo_dealer_yakuman(self):
        """Pao tsumo as dealer: liable player pays the full amount."""
        game_state = self._create_game_state()
        # seat 0 (dealer) wins with pao on seat 3
        # dealer yakuman tsumo: each non-dealer pays 16000
        round_state = update_player(game_state.round_state, 0, pao_seat=3)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )

        # total would be: 16000 * 3 = 48000
        assert result.pao_seat == 3
        assert new_round_state.players[0].score == 25000 + 48000
        assert new_round_state.players[1].score == 25000
        assert new_round_state.players[2].score == 25000
        assert new_round_state.players[3].score == 25000 - 48000

    def test_pao_tsumo_with_riichi_sticks(self):
        """Pao tsumo: riichi sticks still go to winner."""
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 1, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "riichi_sticks": 2})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=1, hand_result=hand_result
        )

        # total tsumo: 32000 + 2000 riichi bonus
        assert new_round_state.players[1].score == 25000 + 34000
        assert new_round_state.players[2].score == 25000 - 32000
        assert result.riichi_sticks_collected == 2

    def test_pao_tsumo_with_honba(self):
        """Pao tsumo with honba: liable player pays full honba too."""
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 1, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "honba_sticks": 2})
        hand_result = HandResult(han=13, fu=30, cost_main=16000, cost_additional=8000, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_tsumo_score(
            game_state, winner_seat=1, hand_result=hand_result
        )

        # honba: 100 per loser * 2 sticks = 200 per loser, 600 total
        # total normal: 32000 + 600 honba = 32600
        assert new_round_state.players[1].score == 25000 + 32600
        assert new_round_state.players[2].score == 25000 - 32600

    def test_no_pao_tsumo_normal_scoring(self):
        """Without pao, tsumo scoring is normal."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_tsumo_score(
            game_state, winner_seat=1, hand_result=hand_result
        )

        assert result.pao_seat is None
        assert new_round_state.players[0].score == 25000 - 1000
        assert new_round_state.players[1].score == 25000 + 2000
        assert new_round_state.players[2].score == 25000 - 500
        assert new_round_state.players[3].score == 25000 - 500


class TestPaoRonScoring:
    """Tests for pao (liability) in ron wins."""

    def _create_game_state(self) -> MahjongGameState:
        """Create a game state with 4 players starting at 25000."""
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_pao_ron_different_player(self):
        """Pao ron: when pao player != loser, payment is split 50/50."""
        game_state = self._create_game_state()
        # seat 0 wins by ron off seat 1, pao on seat 2
        round_state = update_player(game_state.round_state, 0, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        # 32000 split: loser pays 16000, pao pays 16000
        assert result.pao_seat == 2
        assert new_round_state.players[0].score == 25000 + 32000
        assert new_round_state.players[1].score == 25000 - 16000
        assert new_round_state.players[2].score == 25000 - 16000
        assert new_round_state.players[3].score == 25000

    def test_pao_ron_same_player(self):
        """Pao ron: when pao player == loser, normal ron applies."""
        game_state = self._create_game_state()
        # seat 0 wins by ron off seat 1, pao also on seat 1
        round_state = update_player(game_state.round_state, 0, pao_seat=1)
        game_state = game_state.model_copy(update={"round_state": round_state})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        # pao == loser: normal ron, loser pays full
        assert result.pao_seat == 1
        assert new_round_state.players[0].score == 25000 + 32000
        assert new_round_state.players[1].score == 25000 - 32000
        assert new_round_state.players[2].score == 25000
        assert new_round_state.players[3].score == 25000

    def test_pao_ron_with_honba(self):
        """Pao ron with honba: honba is included in the split."""
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 0, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "honba_sticks": 2})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, _result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        # total: 32000 + 600 honba = 32600, split: 16300 each
        assert new_round_state.players[0].score == 25000 + 32600
        assert new_round_state.players[1].score == 25000 - 16300
        assert new_round_state.players[2].score == 25000 - 16300

    def test_pao_ron_with_riichi_sticks(self):
        """Pao ron: riichi sticks still go to winner."""
        game_state = self._create_game_state()
        round_state = update_player(game_state.round_state, 0, pao_seat=2)
        game_state = game_state.model_copy(update={"round_state": round_state, "riichi_sticks": 1})
        hand_result = HandResult(han=13, fu=30, cost_main=32000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        # 32000 split: loser 16000, pao 16000; winner also gets 1000 riichi
        assert new_round_state.players[0].score == 25000 + 33000
        assert new_round_state.players[1].score == 25000 - 16000
        assert new_round_state.players[2].score == 25000 - 16000
        assert result.riichi_sticks_collected == 1

    def test_no_pao_ron_normal_scoring(self):
        """Without pao, ron scoring is normal."""
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        new_round_state, _new_game_state, result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )

        assert result.pao_seat is None
        assert new_round_state.players[0].score == 25000 + 2000
        assert new_round_state.players[1].score == 25000 - 2000


class TestChankanYakuScoring:
    """Test that chankan yaku is correctly credited in hand value calculation."""

    def test_chankan_yaku_credited_in_hand_value(self):
        """Chankan win should include chankan yaku (1 han) in scoring."""
        # setup: player with riichi hand waiting on a tile
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]  # 5p
        settings = GameSettings()
        result = calculate_hand_value(
            player, round_state, win_tile, settings, is_tsumo=False, is_chankan=True
        )

        assert result.error is None
        assert any(y.yaku_id == 4 for y in result.yaku)  # Chankan
        # riichi + chankan = 2 han
        assert result.han >= 2

    def test_chankan_only_yaku_for_open_hand(self):
        """Open hand with no other yaku should succeed when is_chankan=True."""
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
        result = calculate_hand_value(
            player, round_state, win_tile, settings, is_tsumo=False, is_chankan=True
        )

        # chankan provides the yaku, hand should succeed
        assert result.error is None
        assert any(y.yaku_id == 4 for y in result.yaku)  # Chankan
        assert result.han >= 1

    def test_chankan_only_yaku_for_open_hand_fails_without_flag(self):
        """Open hand with no other yaku fails without is_chankan flag."""
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
        result = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=False)

        # without chankan flag, the open hand has no yaku
        assert result.error == "no_yaku"


class TestHandValueParityBetweenFunctions:
    """Verify calculate_hand_value and calculate_hand_value_with_tiles produce identical results."""

    def test_tsumo_parity(self):
        """Both functions return the same result for a tsumo hand."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles))
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result_a = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=True)
        result_b = calculate_hand_value_with_tiles(
            player, round_state, tiles, win_tile, settings, is_tsumo=True
        )

        assert result_a.han == result_b.han
        assert result_a.fu == result_b.fu
        assert result_a.cost_main == result_b.cost_main
        assert result_a.cost_additional == result_b.cost_additional
        assert result_a.yaku == result_b.yaku
        assert result_a.error == result_b.error

    def test_ron_parity_with_riichi(self):
        """Both functions return the same result for a riichi ron hand."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result_a = calculate_hand_value(player, round_state, win_tile, settings, is_tsumo=False)
        result_b = calculate_hand_value_with_tiles(
            player, round_state, tiles, win_tile, settings, is_tsumo=False
        )

        assert result_a.han == result_b.han
        assert result_a.fu == result_b.fu
        assert result_a.cost_main == result_b.cost_main
        assert result_a.yaku == result_b.yaku
        assert result_a.error == result_b.error

    def test_chankan_parity(self):
        """Both functions return the same result with is_chankan flag."""
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        game_state = _create_scoring_game_state()
        round_state = update_player(game_state.round_state, 0, tiles=tuple(tiles), is_riichi=True)
        player = round_state.players[0]

        win_tile = tiles[-1]
        settings = GameSettings()
        result_a = calculate_hand_value(
            player, round_state, win_tile, settings, is_tsumo=False, is_chankan=True
        )
        result_b = calculate_hand_value_with_tiles(
            player, round_state, tiles, win_tile, settings, is_tsumo=False, is_chankan=True
        )

        assert result_a.han == result_b.han
        assert result_a.fu == result_b.fu
        assert result_a.cost_main == result_b.cost_main
        assert result_a.yaku == result_b.yaku

    def test_error_parity(self):
        """Both functions return the same error for invalid hands."""
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
        result_a = calculate_hand_value(player, round_state, win_tile[0], settings, is_tsumo=True)
        result_b = calculate_hand_value_with_tiles(
            player, round_state, list(all_tiles), win_tile[0], settings, is_tsumo=True
        )

        assert result_a.error == result_b.error == "no_yaku"


class TestScoreApplicationRiichiClearing:
    """Verify _apply_score_changes correctly handles riichi stick clearing."""

    def _create_game_state(self) -> MahjongGameState:
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=3)

    def test_tsumo_clears_riichi_sticks(self):
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, new_game_state, _result = apply_tsumo_score(
            game_state, winner_seat=0, hand_result=hand_result
        )
        assert new_game_state.riichi_sticks == 0

    def test_ron_clears_riichi_sticks(self):
        game_state = self._create_game_state()
        hand_result = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        _new_round_state, new_game_state, _result = apply_ron_score(
            game_state, winner_seat=0, loser_seat=1, hand_result=hand_result, winning_tile=0
        )
        assert new_game_state.riichi_sticks == 0

    def test_double_ron_clears_riichi_sticks(self):
        game_state = self._create_game_state()
        hand_result_1 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))
        hand_result_2 = HandResult(han=2, fu=30, cost_main=2000, cost_additional=0, yaku=_yaku(0))

        winners = [(0, hand_result_1), (2, hand_result_2)]
        _new_round_state, new_game_state, _result = apply_double_ron_score(
            game_state, winners=winners, loser_seat=1, winning_tile=0
        )
        assert new_game_state.riichi_sticks == 0

    def test_nagashi_mangan_preserves_riichi_sticks(self):
        game_state = self._create_game_state()

        _new_round_state, new_game_state, _result = apply_nagashi_mangan_score(
            game_state, qualifying_seats=[0], tempai_seats=[], noten_seats=[0, 1, 2, 3], tenpai_hands=[]
        )
        assert new_game_state.riichi_sticks == 3


class TestCollectDoraIndicators:
    """Tests for _collect_dora_indicators settings toggles."""

    def test_omote_dora_disabled_returns_empty(self):
        """When has_omote_dora=False, face-up dora indicators are not collected."""
        settings = GameSettings(has_omote_dora=False)
        round_state = create_round_state(
            dora_indicators=(10, 20),
        )
        result = _collect_dora_indicators(round_state, settings)
        assert result == []


class TestCollectUraDoraIndicators:
    """Tests for collect_ura_dora_indicators()."""

    def test_riichi_player_returns_indicators(self):
        """Riichi player with ura dora enabled gets ura dora indicator list."""
        # dead wall: indices 0-6 top row, 7-13 bottom row
        # ura dora starts at index 7
        dead_wall = tuple(range(100, 114))  # 14 tiles
        settings = GameSettings(has_uradora=True)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),  # 1 dora indicator
        )
        player = create_player(seat=0, is_riichi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result == [dead_wall[7]]

    def test_non_riichi_player_returns_none(self):
        """Non-riichi player gets None."""
        dead_wall = tuple(range(100, 114))
        settings = GameSettings(has_uradora=True)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
        )
        player = create_player(seat=0, is_riichi=False)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result is None

    def test_ura_dora_disabled_returns_none(self):
        """Ura dora disabled returns None even for riichi player."""
        dead_wall = tuple(range(100, 114))
        settings = GameSettings(has_uradora=False)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
        )
        player = create_player(seat=0, is_riichi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result is None

    def test_kan_ura_dora_enabled_multiple_indicators(self):
        """With kan ura dora enabled, returns indicators matching dora count."""
        dead_wall = tuple(range(100, 114))
        settings = GameSettings(has_uradora=True, has_kan_uradora=True)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),  # 2 dora indicators (1 kan)
        )
        player = create_player(seat=0, is_riichi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result == [dead_wall[7], dead_wall[8]]

    def test_kan_ura_dora_disabled_returns_single(self):
        """With kan ura dora disabled, returns only 1 indicator even with multiple dora."""
        dead_wall = tuple(range(100, 114))
        settings = GameSettings(has_uradora=True, has_kan_uradora=False)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),  # 2 dora indicators
        )
        player = create_player(seat=0, is_riichi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result == [dead_wall[7]]

    def test_empty_dead_wall_returns_none(self):
        """Empty dead wall returns None."""
        settings = GameSettings(has_uradora=True)
        round_state = create_round_state(
            dead_wall=(),
            dora_indicators=(10,),
        )
        player = create_player(seat=0, is_riichi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result is None

    def test_no_dora_indicators_returns_none(self):
        """No dora indicators returns None."""
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
    """Verify ura dora indicators are passed separately and affect hand value scoring."""

    # disable aka dora for precise han counting
    settings_no_aka = GameSettings(has_akadora=False)
    settings_no_aka_no_ura = GameSettings(has_akadora=False, has_uradora=False)

    def _build_game_state(self, *, dead_wall, dora_indicators, tiles, is_riichi):
        """Build a game state with controlled dead wall for ura dora testing."""
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

    def test_riichi_tsumo_with_matching_ura_dora(self):
        """Riichi tsumo where ura dora indicator matches tiles in hand adds extra han."""
        # hand: 123m 456m 789m 12s 55s (riichi tsumo)
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        # dora indicator: 1m -> dora is 2m (1 copy in hand = 1 han)
        dora_indicator = TilesConverter.string_to_136_array(man="1")

        # dead wall: index 2 = dora indicator, index 7 = ura dora indicator
        # ura dora indicator: 4s -> ura dora is 5s (2 copies in hand = 2 han)
        ura_dora_tile = TilesConverter.string_to_136_array(sou="4")[0]
        dead_wall = [0] * 14
        dead_wall[2] = dora_indicator[0]
        dead_wall[7] = ura_dora_tile

        game_state = self._build_game_state(
            dead_wall=tuple(dead_wall),
            dora_indicators=tuple(dora_indicator),
            tiles=tiles,
            is_riichi=True,
        )
        player = game_state.round_state.players[0]
        result = calculate_hand_value(
            player, game_state.round_state, win_tile, self.settings_no_aka, is_tsumo=True
        )

        assert result.error is None
        assert any(y.yaku_id == 122 and y.han == 2 for y in result.yaku)  # Ura Dora 2
        # Menzen Tsumo (1) + Riichi (1) + Ittsu (1) + Dora 1 (1) + Ura Dora 2 (2) = 7 han
        assert result.han == 7

    def test_riichi_tsumo_without_matching_ura_dora(self):
        """Riichi tsumo where ura dora indicator doesn't match any hand tile gives no ura dora han."""
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        dora_indicator = TilesConverter.string_to_136_array(man="1")

        # ura dora indicator: 6s -> ura dora is 7s (not in hand)
        ura_dora_tile = TilesConverter.string_to_136_array(sou="6")[0]
        dead_wall = [0] * 14
        dead_wall[2] = dora_indicator[0]
        dead_wall[7] = ura_dora_tile

        game_state = self._build_game_state(
            dead_wall=tuple(dead_wall),
            dora_indicators=tuple(dora_indicator),
            tiles=tiles,
            is_riichi=True,
        )
        player = game_state.round_state.players[0]
        result = calculate_hand_value(
            player, game_state.round_state, win_tile, self.settings_no_aka, is_tsumo=True
        )

        assert result.error is None
        assert not any(y.yaku_id == 122 for y in result.yaku)  # no Ura Dora
        # Menzen Tsumo (1) + Riichi (1) + Ittsu (1) + Dora 1 (1) = 5 han
        assert result.han == 5

    def test_non_riichi_win_gets_no_ura_dora(self):
        """Non-riichi win does not receive ura dora even if indicator matches."""
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        dora_indicator = TilesConverter.string_to_136_array(man="1")

        # ura dora indicator: 4s -> ura dora is 5s (would match, but no riichi)
        ura_dora_tile = TilesConverter.string_to_136_array(sou="4")[0]
        dead_wall = [0] * 14
        dead_wall[2] = dora_indicator[0]
        dead_wall[7] = ura_dora_tile

        game_state = self._build_game_state(
            dead_wall=tuple(dead_wall),
            dora_indicators=tuple(dora_indicator),
            tiles=tiles,
            is_riichi=False,
        )
        player = game_state.round_state.players[0]
        result = calculate_hand_value(
            player, game_state.round_state, win_tile, self.settings_no_aka, is_tsumo=True
        )

        assert result.error is None
        assert not any(y.yaku_id == 122 for y in result.yaku)  # no Ura Dora

    def test_riichi_ron_with_matching_ura_dora(self):
        """Riichi ron where ura dora indicator matches tiles in hand adds extra han."""
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        dora_indicator = TilesConverter.string_to_136_array(man="1")

        ura_dora_tile = TilesConverter.string_to_136_array(sou="4")[0]
        dead_wall = [0] * 14
        dead_wall[2] = dora_indicator[0]
        dead_wall[7] = ura_dora_tile

        game_state = self._build_game_state(
            dead_wall=tuple(dead_wall),
            dora_indicators=tuple(dora_indicator),
            tiles=tiles,
            is_riichi=True,
        )
        player = game_state.round_state.players[0]
        result = calculate_hand_value(
            player, game_state.round_state, win_tile, self.settings_no_aka, is_tsumo=False
        )

        assert result.error is None
        assert any(y.yaku_id == 122 and y.han == 2 for y in result.yaku)  # Ura Dora 2
        # Riichi (1) + Ittsu (1) + Dora 1 (1) + Ura Dora 2 (2) = 6 han (no menzen tsumo for ron)
        assert result.han == 6

    def test_ura_dora_disabled_in_settings(self):
        """Ura dora disabled in settings means no ura dora even for riichi with matching indicator."""
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        dora_indicator = TilesConverter.string_to_136_array(man="1")

        ura_dora_tile = TilesConverter.string_to_136_array(sou="4")[0]
        dead_wall = [0] * 14
        dead_wall[2] = dora_indicator[0]
        dead_wall[7] = ura_dora_tile

        game_state = self._build_game_state(
            dead_wall=tuple(dead_wall),
            dora_indicators=tuple(dora_indicator),
            tiles=tiles,
            is_riichi=True,
        )
        player = game_state.round_state.players[0]
        result = calculate_hand_value(
            player, game_state.round_state, win_tile, self.settings_no_aka_no_ura, is_tsumo=True
        )

        assert result.error is None
        assert not any(y.yaku_id == 122 for y in result.yaku)  # no Ura Dora
        # Menzen Tsumo (1) + Riichi (1) + Ittsu (1) + Dora 1 (1) = 5 han
        assert result.han == 5

    def test_kan_ura_dora_multiple_indicators(self):
        """With kan ura dora enabled and multiple dora indicators, multiple ura dora are checked."""
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
        result = calculate_hand_value(player, game_state.round_state, win_tile, settings, is_tsumo=True)

        assert result.error is None
        assert any(y.yaku_id == 122 and y.han == 3 for y in result.yaku)  # Ura Dora 3
