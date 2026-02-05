"""
Unit tests for round initialization and management.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import BotType, RoundPhase
from game.logic.round import (
    DEAD_WALL_SIZE,
    FIRST_DORA_INDEX,
    MAX_DORA_INDICATORS,
    add_dora_indicator,
    create_players,
    init_round,
)
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState
from game.logic.types import SeatConfig
from game.tests.unit.helpers import _string_to_34_tiles


class TestInitRound:
    def _create_game_state_with_players(self) -> MahjongGameState:
        """Create a game state with 4 players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        round_state = MahjongRoundState(players=players, dealer_seat=0)
        return MahjongGameState(round_state=round_state, seed=12345.0, round_number=0)

    def test_init_round_creates_wall(self):
        game_state = self._create_game_state_with_players()
        init_round(game_state)

        round_state = game_state.round_state
        # wall should have 136 - 14 (dead wall) - 52 (dealt) = 70 tiles
        total_tiles = 136
        dealt_tiles = 13 * 4
        expected_wall = total_tiles - DEAD_WALL_SIZE - dealt_tiles
        assert len(round_state.wall) == expected_wall

    def test_init_round_creates_dead_wall(self):
        game_state = self._create_game_state_with_players()
        init_round(game_state)

        round_state = game_state.round_state
        assert len(round_state.dead_wall) == DEAD_WALL_SIZE

    def test_init_round_sets_dora_indicator(self):
        game_state = self._create_game_state_with_players()
        init_round(game_state)

        round_state = game_state.round_state
        assert len(round_state.dora_indicators) == 1
        # first dora is at dead_wall[2]
        assert round_state.dora_indicators[0] == round_state.dead_wall[FIRST_DORA_INDEX]

    def test_init_round_deals_13_tiles_to_each_player(self):
        game_state = self._create_game_state_with_players()
        init_round(game_state)

        round_state = game_state.round_state
        for player in round_state.players:
            assert len(player.tiles) == 13

    def test_init_round_all_tiles_unique(self):
        game_state = self._create_game_state_with_players()
        init_round(game_state)

        round_state = game_state.round_state
        # collect all tiles dealt
        all_dealt = []
        for player in round_state.players:
            all_dealt.extend(player.tiles)

        # all tiles in wall
        all_dealt.extend(round_state.wall)
        all_dealt.extend(round_state.dead_wall)

        # should be exactly 136 unique tiles
        assert len(all_dealt) == 136
        assert len(set(all_dealt)) == 136

    def test_init_round_sorts_player_hands(self):
        game_state = self._create_game_state_with_players()
        init_round(game_state)

        round_state = game_state.round_state
        for player in round_state.players:
            assert player.tiles == sorted(player.tiles)

    def test_init_round_sets_current_player_to_dealer(self):
        game_state = self._create_game_state_with_players()
        game_state.round_state.dealer_seat = 2
        init_round(game_state)

        assert game_state.round_state.current_player_seat == 2

    def test_init_round_resets_player_states(self):
        game_state = self._create_game_state_with_players()
        # set some state that should be reset
        game_state.round_state.players[0].is_riichi = True
        game_state.round_state.players[1].is_ippatsu = True
        game_state.round_state.players[2].is_daburi = True
        game_state.round_state.players[3].is_rinshan = True
        game_state.round_state.players[0].kuikae_tiles = _string_to_34_tiles(man="12")
        game_state.round_state.players[1].pao_seat = 2

        init_round(game_state)

        round_state = game_state.round_state
        for player in round_state.players:
            assert player.is_riichi is False
            assert player.is_ippatsu is False
            assert player.is_daburi is False
            assert player.is_rinshan is False
            assert player.kuikae_tiles == []
            assert player.pao_seat is None
            assert player.discards == []
            assert player.melds == []

    def test_init_round_resets_tracking(self):
        game_state = self._create_game_state_with_players()
        game_state.round_state.turn_count = 10
        game_state.round_state.all_discards = TilesConverter.string_to_136_array(man="1111")[1:]
        game_state.round_state.players_with_open_hands = [1, 2]

        init_round(game_state)

        round_state = game_state.round_state
        assert round_state.turn_count == 0
        assert round_state.all_discards == []
        assert round_state.players_with_open_hands == []

    def test_init_round_sets_phase_to_playing(self):
        game_state = self._create_game_state_with_players()
        init_round(game_state)

        assert game_state.round_state.phase == RoundPhase.PLAYING

    def test_init_round_reproducible_with_same_seed(self):
        game_state1 = self._create_game_state_with_players()
        game_state2 = self._create_game_state_with_players()

        init_round(game_state1)
        init_round(game_state2)

        # both should have identical walls and hands
        assert game_state1.round_state.wall == game_state2.round_state.wall
        assert game_state1.round_state.dead_wall == game_state2.round_state.dead_wall
        for i in range(4):
            assert game_state1.round_state.players[i].tiles == game_state2.round_state.players[i].tiles

    def test_init_round_different_with_different_seed(self):
        game_state1 = self._create_game_state_with_players()
        game_state1.seed = 12345.0
        game_state2 = self._create_game_state_with_players()
        game_state2.seed = 67890.0

        init_round(game_state1)
        init_round(game_state2)

        # walls should be different
        assert game_state1.round_state.wall != game_state2.round_state.wall

    def test_init_round_different_with_different_round_number(self):
        game_state1 = self._create_game_state_with_players()
        game_state1.round_number = 0
        game_state2 = self._create_game_state_with_players()
        game_state2.round_number = 1

        init_round(game_state1)
        init_round(game_state2)

        # walls should be different
        assert game_state1.round_state.wall != game_state2.round_state.wall

    def test_init_round_dealer_deals_first(self):
        game_state = self._create_game_state_with_players()
        game_state.round_state.dealer_seat = 2
        game_state.seed = 99999.0
        init_round(game_state)

        # create second game with dealer at 0 and same seed
        game_state2 = self._create_game_state_with_players()
        game_state2.round_state.dealer_seat = 0
        game_state2.seed = 99999.0
        init_round(game_state2)

        # dealer gets the first dealt tiles, so seat 2 in first game
        # should have same tiles as seat 0 in second game
        assert game_state.round_state.players[2].tiles == game_state2.round_state.players[0].tiles


class TestAddDoraIndicator:
    def _create_round_state_with_dead_wall(self) -> MahjongRoundState:
        """Create a round state with a dead wall for testing."""
        # 14 tiles: North(copies 2-3), Haku(4), Hatsu(4), Chun(4)
        dead_wall = [
            *TilesConverter.string_to_136_array(honors="4444")[2:],
            *TilesConverter.string_to_136_array(honors="555566667777"),
        ]
        return MahjongRoundState(
            dead_wall=dead_wall,
            dora_indicators=[dead_wall[FIRST_DORA_INDEX]],  # first dora at index 2
        )

    def test_add_dora_indicator_adds_second_dora(self):
        round_state = self._create_round_state_with_dead_wall()
        assert len(round_state.dora_indicators) == 1

        new_indicator = add_dora_indicator(round_state)

        assert len(round_state.dora_indicators) == 2
        assert new_indicator == round_state.dead_wall[3]
        assert round_state.dora_indicators[1] == round_state.dead_wall[3]

    def test_add_dora_indicator_adds_third_dora(self):
        round_state = self._create_round_state_with_dead_wall()
        add_dora_indicator(round_state)

        new_indicator = add_dora_indicator(round_state)

        assert len(round_state.dora_indicators) == 3
        assert new_indicator == round_state.dead_wall[4]

    def test_add_dora_indicator_adds_fourth_dora(self):
        round_state = self._create_round_state_with_dead_wall()
        add_dora_indicator(round_state)
        add_dora_indicator(round_state)

        new_indicator = add_dora_indicator(round_state)

        assert len(round_state.dora_indicators) == 4
        assert new_indicator == round_state.dead_wall[5]

    def test_add_dora_indicator_adds_fifth_dora(self):
        round_state = self._create_round_state_with_dead_wall()
        add_dora_indicator(round_state)
        add_dora_indicator(round_state)
        add_dora_indicator(round_state)

        new_indicator = add_dora_indicator(round_state)

        assert len(round_state.dora_indicators) == 5
        assert new_indicator == round_state.dead_wall[6]

    def test_add_dora_indicator_raises_when_max_reached(self):
        round_state = self._create_round_state_with_dead_wall()
        # add up to max (initial + 4 kans = 5 indicators)
        for _ in range(MAX_DORA_INDICATORS - 1):
            add_dora_indicator(round_state)

        assert len(round_state.dora_indicators) == MAX_DORA_INDICATORS

        # next add should raise
        with pytest.raises(ValueError, match="cannot add more than 5 dora indicators"):
            add_dora_indicator(round_state)


class TestCreatePlayers:
    def _default_configs(self) -> list[SeatConfig]:
        return [
            SeatConfig(name="Human"),
            SeatConfig(name="Tsumogiri 1", bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="Tsumogiri 2", bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="Tsumogiri 3", bot_type=BotType.TSUMOGIRI),
        ]

    def test_create_players_creates_four_players(self):
        configs = self._default_configs()
        players = create_players(configs)

        assert len(players) == 4

    def test_create_players_first_is_human(self):
        configs = self._default_configs()
        players = create_players(configs)

        assert players[0].name == "Human"
        assert players[0].seat == 0

    def test_create_players_rest_are_bots(self):
        configs = self._default_configs()
        players = create_players(configs)

        for i in range(1, 4):
            assert players[i].seat == i

    def test_create_players_assigns_correct_names(self):
        configs = [
            SeatConfig(name="Alice"),
            SeatConfig(name="BotA", bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="BotB", bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="BotC", bot_type=BotType.TSUMOGIRI),
        ]
        players = create_players(configs)

        assert players[0].name == "Alice"
        assert players[1].name == "BotA"
        assert players[2].name == "BotB"
        assert players[3].name == "BotC"

    def test_create_players_default_scores(self):
        configs = self._default_configs()
        players = create_players(configs)

        for player in players:
            assert player.score == 25000
