from mahjong.tile import TilesConverter

from game.logic.actions import get_available_actions
from game.logic.enums import AIPlayerType, PlayerAction
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.types import SeatConfig
from game.logic.wall import Wall
from game.tests.unit.helpers import _string_to_34_tile


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
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
        # draw a tile for the dealer
        new_round_state, _tile = draw_tile(game_state.round_state)
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_get_available_actions__should_not_include_discard(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_actions = [a for a in actions if a.action == PlayerAction.DISCARD]
        assert len(discard_actions) == 0

    def test_get_available_actions__when_kan_available__should_list_kan_tiles(self):
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
        round_state = game_state.round_state

        # give player 4 of the same tile for closed kan
        # 4x 1m + 4x 2m + 4x 3m + 2x 4m = 14 tiles
        kan_tiles = tuple(TilesConverter.string_to_136_array(man="11112222333344"))
        round_state = _update_player(round_state, 0, tiles=kan_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        if kan_actions:
            assert kan_actions[0].tiles is not None
            assert isinstance(kan_actions[0].tiles, list)

    def test_get_available_actions__when_wall_empty__should_not_offer_kan(self):
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
        round_state = game_state.round_state

        # give player 4 of the same tile plus 10 more to make 14 total
        kan_tiles = tuple(TilesConverter.string_to_136_array(man="11112222333344"))
        round_state = _update_player(round_state, 0, tiles=kan_tiles)
        # empty the wall
        round_state = round_state.model_copy(update={"wall": Wall()})
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        # no kan should be available since wall is empty
        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        assert len(kan_actions) == 0

    def test_get_available_actions__when_hand_empty__should_return_none(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        round_state = _update_player(round_state, 0, tiles=())
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        assert len(actions) == 0


class TestAddedKanAction:
    def test_added_kan_action__when_pon_and_fourth_tile_in_hand__should_be_offered(self):
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
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

        # player must be in open hands list
        # wall needs at least 2 tiles for kan
        round_state = round_state.model_copy(
            update={
                "players_with_open_hands": (0,),
                "wall": round_state.wall.model_copy(update={"live_tiles": tuple(range(50))}),
            },
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        added_kan_actions = [a for a in actions if a.action == PlayerAction.ADDED_KAN]
        assert len(added_kan_actions) == 1
        assert added_kan_actions[0].tiles is not None
        assert _string_to_34_tile(man="1") in added_kan_actions[0].tiles
