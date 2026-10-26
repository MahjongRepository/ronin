import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_tsumo
from game.logic.actions import get_available_actions
from game.logic.enums import AIPlayerType, PlayerAction
from game.logic.exceptions import InvalidGameActionError
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.types import SeatConfig
from game.tests.helpers.wall import make_wall
from game.tests.unit.helpers import _string_to_34_tile, _string_to_34_tiles


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


def _update_player(round_state, seat, **updates: object):
    players = list(round_state.players)
    players[seat] = players[seat].model_copy(update=updates)
    return round_state.model_copy(update={"players": tuple(players)})


class TestGetAvailableActions:
    def _create_game_state(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        # draw a tile for the dealer
        new_round_state, _tile = draw_tile(game_state.round_state)
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_get_available_actions__should_not_include_discard(self):
        game_state = self._create_game_state()

        actions = get_available_actions(game_state, seat=0)
        discard_actions = [a for a in actions if a.action == PlayerAction.DISCARD]
        assert len(discard_actions) == 0

    def test_get_available_actions__when_closed_hand_can_riichi__should_list_only_tenpai_keeping_discards(self):
        game_state = self._create_game_state()
        pin_ones = TilesConverter.string_to_136_array(pin="11")
        stray_tile = TilesConverter.string_to_136_array(sou="9")[0]
        hand = (
            *TilesConverter.string_to_136_array(man="123456789"),
            *pin_ones,
            *TilesConverter.string_to_136_array(pin="23"),
            stray_tile,
        )
        round_state = _update_player(game_state.round_state, 0, tiles=hand)
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(game_state, seat=0)
        riichi_actions = [a for a in actions if a.action == PlayerAction.RIICHI]
        assert len(riichi_actions) == 1
        assert riichi_actions[0].tiles == [*pin_ones, stray_tile]

    def test_get_available_actions__when_kan_available__should_list_kan_tiles(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 4 of the same tile for closed kan
        # 4x 1m + 4x 2m + 4x 3m + 2x 4m = 14 tiles
        kan_tiles = tuple(TilesConverter.string_to_136_array(man="11112222333344"))
        round_state = _update_player(round_state, 0, tiles=kan_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(game_state, seat=0)
        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        assert len(kan_actions) == 1
        assert kan_actions[0].tiles == _string_to_34_tiles(man="123")

    def test_get_available_actions__when_wall_empty__should_not_offer_kan(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 4 of the same tile plus 10 more to make 14 total
        kan_tiles = tuple(TilesConverter.string_to_136_array(man="11112222333344"))
        round_state = _update_player(round_state, 0, tiles=kan_tiles)
        # empty the wall
        round_state = round_state.model_copy(update={"wall": make_wall()})
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(game_state, seat=0)
        # no kan should be available since wall is empty
        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        assert len(kan_actions) == 0

    def test_get_available_actions__when_hand_empty__should_return_none(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        round_state = _update_player(round_state, 0, tiles=())
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(game_state, seat=0)
        assert len(actions) == 0


class TestTsumoAfterOwnCall:
    def test_tsumo__when_hand_complete_right_after_own_pon__should_be_neither_offered_nor_accepted(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        haku_pon = FrozenMeld(
            meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, called_tile=haku_tiles[0], who=0, from_who=3
        )
        complete_hand = tuple(TilesConverter.string_to_136_array(man="234567", sou="23455"))
        round_state = _update_player(game_state.round_state, 0, tiles=complete_hand, melds=(haku_pon,))
        drawn_state = round_state.model_copy(update={"current_player_seat": 0})
        after_pon_state = drawn_state.model_copy(update={"is_after_meld_call": True})

        drawn_actions = get_available_actions(game_state.model_copy(update={"round_state": drawn_state}), seat=0)
        assert PlayerAction.TSUMO in [a.action for a in drawn_actions]

        after_pon_game = game_state.model_copy(update={"round_state": after_pon_state})
        after_pon_actions = get_available_actions(after_pon_game, seat=0)
        assert PlayerAction.TSUMO not in [a.action for a in after_pon_actions]
        with pytest.raises(InvalidGameActionError, match="cannot declare tsumo"):
            handle_tsumo(after_pon_game, seat=0)


class TestAddedKanAction:
    def test_added_kan_action__when_pon_and_fourth_tile_in_hand__should_be_offered(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # set up player with a pon of 1m and 4th tile in hand
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
            called_tile=TilesConverter.string_to_136_array(man="111")[2],
            who=0,
            from_who=1,
        )
        player_tiles = (
            TilesConverter.string_to_136_array(man="1111")[3],
            *TilesConverter.string_to_136_array(pin="1234", sou="1234", honors="12345"),
        )
        round_state = _update_player(round_state, 0, melds=(pon_meld,), tiles=player_tiles)

        # wall needs at least 2 tiles for kan
        round_state = round_state.model_copy(
            update={
                "wall": round_state.wall.model_copy(update={"live_tiles": tuple(range(50))}),
            },
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(game_state, seat=0)
        added_kan_actions = [a for a in actions if a.action == PlayerAction.ADDED_KAN]
        assert len(added_kan_actions) == 1
        assert added_kan_actions[0].tiles == [_string_to_34_tile(man="1")]
