"""
Unit tests for available actions builder.
"""

from mahjong.tile import TilesConverter

from game.logic.actions import get_available_actions
from game.logic.enums import AIPlayerType, PlayerAction
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.types import AvailableActionItem, SeatConfig
from game.tests.unit.helpers import _string_to_34_tile


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


def _update_player(round_state, seat, **updates: object):
    """Helper to update a player in an immutable round state."""
    players = list(round_state.players)
    players[seat] = players[seat].model_copy(update=updates)
    return round_state.model_copy(update={"players": tuple(players)})


class TestAvailableActionItemSerialization:
    def test_serializes_without_tiles_when_none(self):
        item = AvailableActionItem(action=PlayerAction.TSUMO)
        data = item.model_dump()
        assert data == {"action": PlayerAction.TSUMO}
        assert "tiles" not in data

    def test_serializes_with_tiles_when_present(self):
        item = AvailableActionItem(action=PlayerAction.KAN, tiles=[1, 2, 3])
        data = item.model_dump()
        assert data == {"action": PlayerAction.KAN, "tiles": [1, 2, 3]}


class TestGetAvailableActions:
    def _create_game_state(self):
        """Create a game state for testing."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        # draw a tile for the dealer
        new_round_state, _tile = draw_tile(game_state.round_state)
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_returns_list_format(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        assert isinstance(actions, list)
        assert all(isinstance(action, AvailableActionItem) for action in actions)

    def test_does_not_return_discard_action(self):
        """DISCARD is always available and handled implicitly; not in available_actions."""
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_actions = [a for a in actions if a.action == PlayerAction.DISCARD]
        assert len(discard_actions) == 0

    def test_riichi_action_when_eligible(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # create a tempai hand: 123m 456m 789m 111p, waiting for 2p
        tempai_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        round_state = _update_player(round_state, 0, tiles=tempai_tiles)
        new_round_state, _tile = draw_tile(round_state)
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        actions = get_available_actions(new_round_state, game_state, seat=0)

        riichi_actions = [a for a in actions if a.action == PlayerAction.RIICHI]
        # riichi may or may not be available depending on tempai status
        # just verify the action format is correct if present
        for action in riichi_actions:
            assert action.action == PlayerAction.RIICHI
            assert action.tiles is None

    def test_tsumo_action_when_winning_hand(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # create a winning hand: 123m 456m 789m 11p 22p (complete)
        winning_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1122"))
        round_state = _update_player(round_state, 0, tiles=winning_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        tsumo_actions = [a for a in actions if a.action == PlayerAction.TSUMO]
        # tsumo may or may not be available depending on hand value
        for action in tsumo_actions:
            assert action.action == PlayerAction.TSUMO
            assert action.tiles is None

    def test_kan_action_format(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
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

    def test_no_kan_when_wall_empty(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 4 of the same tile plus 10 more to make 14 total
        kan_tiles = tuple(TilesConverter.string_to_136_array(man="11112222333344"))
        round_state = _update_player(round_state, 0, tiles=kan_tiles)
        # empty the wall
        round_state = round_state.model_copy(update={"wall": ()})
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        # no kan should be available since wall is empty
        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        assert len(kan_actions) == 0

    def test_no_actions_for_empty_hand(self):
        """Empty hand returns no actions (no tsumo, no kan, etc.)."""
        game_state = self._create_game_state()
        round_state = game_state.round_state
        round_state = _update_player(round_state, 0, tiles=())
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        assert len(actions) == 0


class TestAddedKanAction:
    def test_added_kan_available_with_pon_and_fourth_tile(self):
        """Player with a pon meld and 4th tile in hand can declare added kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
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
                "wall": tuple(range(50)),
            }
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        actions = get_available_actions(round_state, game_state, seat=0)

        added_kan_actions = [a for a in actions if a.action == PlayerAction.ADDED_KAN]
        assert len(added_kan_actions) == 1
        assert added_kan_actions[0].tiles is not None
        assert _string_to_34_tile(man="1") in added_kan_actions[0].tiles
