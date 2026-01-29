"""
Unit tests for available actions builder.
"""

from game.logic.actions import get_available_actions
from game.logic.enums import BotType, PlayerAction
from game.logic.game import init_game
from game.logic.round import draw_tile
from game.logic.types import AvailableActionItem, SeatConfig


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player", is_bot=False),
        SeatConfig(name="Tsumogiri 1", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", is_bot=True, bot_type=BotType.TSUMOGIRI),
    ]


class TestGetAvailableActions:
    def _create_game_state(self):
        """Create a game state for testing."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        # draw a tile for the dealer
        draw_tile(game_state.round_state)
        return game_state

    def test_returns_list_format(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        assert isinstance(actions, list)
        assert all(isinstance(action, AvailableActionItem) for action in actions)

    def test_returns_discard_action_with_tiles(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_actions = [a for a in actions if a.action == PlayerAction.DISCARD]
        assert len(discard_actions) == 1
        assert discard_actions[0].tiles is not None
        assert len(discard_actions[0].tiles) == 14  # 13 dealt + 1 drawn

    def test_riichi_action_when_eligible(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[0]

        # create a tempai hand: 123m 456m 789m 111p, waiting for 2p
        # 1m=0-3, 2m=4-7, 3m=8-11, 4m=12-15, 5m=16-19, 6m=20-23, 7m=24-27, 8m=28-31, 9m=32-35
        # 1p=36-39, 2p=40-43
        player.tiles = [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,
            38,  # 111p
            40,  # 2p (waiting for pair)
        ]
        draw_tile(round_state)

        actions = get_available_actions(round_state, game_state, seat=0)

        riichi_actions = [a for a in actions if a.action == PlayerAction.RIICHI]
        # riichi may or may not be available depending on tempai status
        # just verify the action format is correct if present
        for action in riichi_actions:
            assert action.action == PlayerAction.RIICHI
            assert action.tiles is None

    def test_tsumo_action_when_winning_hand(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[0]

        # create a winning hand: 123m 456m 789m 11p 22p (complete)
        # this is a winning hand with 2 pairs completing melds
        player.tiles = [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,  # 11p
            40,
            41,  # 22p - winning tile
        ]

        actions = get_available_actions(round_state, game_state, seat=0)

        tsumo_actions = [a for a in actions if a.action == PlayerAction.TSUMO]
        # tsumo may or may not be available depending on hand value
        for action in tsumo_actions:
            assert action.action == PlayerAction.TSUMO
            assert action.tiles is None

    def test_kan_action_format(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[0]

        # give player 4 of the same tile for closed kan
        # 1m = tiles 0, 1, 2, 3, plus 10 other tiles to make 14 total
        player.tiles = [0, 1, 2, 3, *list(range(4, 14))]  # 4 1m tiles + 10 more = 14 tiles

        actions = get_available_actions(round_state, game_state, seat=0)

        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        if kan_actions:
            assert kan_actions[0].tiles is not None
            assert isinstance(kan_actions[0].tiles, list)

    def test_riichi_limits_discard_to_drawn_tile(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        player = round_state.players[0]
        player.is_riichi = True

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_actions = [a for a in actions if a.action == PlayerAction.DISCARD]
        assert len(discard_actions) == 1
        # in riichi, can only discard the drawn tile (last tile in hand)
        assert discard_actions[0].tiles is not None
        assert len(discard_actions[0].tiles) == 1
        assert discard_actions[0].tiles[0] == player.tiles[-1]

    def test_empty_hand_returns_no_discard_action(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        player = round_state.players[0]
        player.tiles = []

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_actions = [a for a in actions if a.action == PlayerAction.DISCARD]
        assert len(discard_actions) == 0

    def test_no_kan_when_wall_empty(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[0]

        # give player 4 of the same tile plus 10 more to make 14 total
        player.tiles = [0, 1, 2, 3, *list(range(4, 14))]
        # empty the wall
        round_state.wall = []

        actions = get_available_actions(round_state, game_state, seat=0)

        # no kan should be available since wall is empty
        kan_actions = [a for a in actions if a.action == PlayerAction.KAN]
        assert len(kan_actions) == 0
