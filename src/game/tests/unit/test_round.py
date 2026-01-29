"""
Unit tests for round initialization and management.
"""

import pytest

from game.logic.enums import BotType
from game.logic.round import (
    DEAD_WALL_SIZE,
    FIRST_DORA_INDEX,
    MAX_DORA_INDICATORS,
    add_dora_indicator,
    advance_turn,
    check_exhaustive_draw,
    create_players,
    discard_tile,
    draw_from_dead_wall,
    draw_tile,
    init_round,
    is_tempai,
    process_exhaustive_draw,
)
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    RoundPhase,
)
from game.logic.types import SeatConfig


class TestInitRound:
    def _create_game_state_with_players(self) -> MahjongGameState:
        """Create a game state with 4 players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
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

        init_round(game_state)

        round_state = game_state.round_state
        for player in round_state.players:
            assert player.is_riichi is False
            assert player.is_ippatsu is False
            assert player.is_daburi is False
            assert player.is_rinshan is False
            assert player.discards == []
            assert player.melds == []

    def test_init_round_resets_tracking(self):
        game_state = self._create_game_state_with_players()
        game_state.round_state.turn_count = 10
        game_state.round_state.all_discards = [1, 2, 3]
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
        dead_wall = list(range(122, 136))  # 14 tiles
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

    def test_add_dora_indicator_raises_when_max_reached(self):
        round_state = self._create_round_state_with_dead_wall()
        # add up to max
        for _ in range(MAX_DORA_INDICATORS - 1):
            add_dora_indicator(round_state)

        assert len(round_state.dora_indicators) == MAX_DORA_INDICATORS

        # next add should raise
        with pytest.raises(ValueError, match="cannot add more than 4 dora indicators"):
            add_dora_indicator(round_state)


class TestCreatePlayers:
    def _default_configs(self) -> list[SeatConfig]:
        return [
            SeatConfig(name="Human", is_bot=False),
            SeatConfig(name="Tsumogiri 1", is_bot=True, bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="Tsumogiri 2", is_bot=True, bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="Tsumogiri 3", is_bot=True, bot_type=BotType.TSUMOGIRI),
        ]

    def test_create_players_creates_four_players(self):
        configs = self._default_configs()
        players = create_players(configs)

        assert len(players) == 4

    def test_create_players_first_is_human(self):
        configs = self._default_configs()
        players = create_players(configs)

        assert players[0].is_bot is False
        assert players[0].name == "Human"
        assert players[0].seat == 0

    def test_create_players_rest_are_bots(self):
        configs = self._default_configs()
        players = create_players(configs)

        for i in range(1, 4):
            assert players[i].is_bot is True
            assert players[i].seat == i

    def test_create_players_assigns_correct_names(self):
        configs = [
            SeatConfig(name="Alice", is_bot=False),
            SeatConfig(name="BotA", is_bot=True, bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="BotB", is_bot=True, bot_type=BotType.TSUMOGIRI),
            SeatConfig(name="BotC", is_bot=True, bot_type=BotType.TSUMOGIRI),
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


class TestDrawTile:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with wall and players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        return MahjongRoundState(
            wall=list(range(10)),  # 10 tiles
            players=players,
            current_player_seat=0,
        )

    def test_draw_tile_removes_from_wall(self):
        round_state = self._create_round_state()
        initial_wall_len = len(round_state.wall)

        draw_tile(round_state)

        assert len(round_state.wall) == initial_wall_len - 1

    def test_draw_tile_returns_first_tile(self):
        round_state = self._create_round_state()
        first_tile = round_state.wall[0]

        drawn = draw_tile(round_state)

        assert drawn == first_tile

    def test_draw_tile_adds_to_player_hand(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 2
        initial_hand_len = len(round_state.players[2].tiles)

        drawn = draw_tile(round_state)

        assert len(round_state.players[2].tiles) == initial_hand_len + 1
        assert drawn in round_state.players[2].tiles

    def test_draw_tile_appends_to_end_of_hand(self):
        round_state = self._create_round_state()
        round_state.players[0].tiles = [100, 101, 102]

        drawn = draw_tile(round_state)

        assert round_state.players[0].tiles[-1] == drawn

    def test_draw_tile_returns_none_when_wall_empty(self):
        round_state = self._create_round_state()
        round_state.wall = []

        drawn = draw_tile(round_state)

        assert drawn is None

    def test_draw_tile_does_not_modify_hand_when_wall_empty(self):
        round_state = self._create_round_state()
        round_state.wall = []
        round_state.players[0].tiles = [100, 101]

        draw_tile(round_state)

        assert round_state.players[0].tiles == [100, 101]


class TestDrawFromDeadWall:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with dead wall and players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        return MahjongRoundState(
            dead_wall=list(range(122, 136)),  # 14 tiles
            players=players,
            current_player_seat=0,
        )

    def test_draw_from_dead_wall_removes_from_dead_wall(self):
        round_state = self._create_round_state()
        initial_len = len(round_state.dead_wall)

        draw_from_dead_wall(round_state)

        assert len(round_state.dead_wall) == initial_len - 1

    def test_draw_from_dead_wall_returns_last_tile(self):
        round_state = self._create_round_state()
        last_tile = round_state.dead_wall[-1]

        drawn = draw_from_dead_wall(round_state)

        assert drawn == last_tile

    def test_draw_from_dead_wall_adds_to_player_hand(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 1
        initial_hand_len = len(round_state.players[1].tiles)

        drawn = draw_from_dead_wall(round_state)

        assert len(round_state.players[1].tiles) == initial_hand_len + 1
        assert drawn in round_state.players[1].tiles

    def test_draw_from_dead_wall_sets_rinshan_flag(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 0
        assert round_state.players[0].is_rinshan is False

        draw_from_dead_wall(round_state)

        assert round_state.players[0].is_rinshan is True


class TestDiscardTile:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[10, 20, 30, 40]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[11, 21, 31, 41]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[12, 22, 32, 42]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[13, 23, 33, 43]),
        ]
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_discard_tile_removes_from_hand(self):
        round_state = self._create_round_state()
        assert 20 in round_state.players[0].tiles

        discard_tile(round_state, seat=0, tile_id=20)

        assert 20 not in round_state.players[0].tiles

    def test_discard_tile_adds_to_discards(self):
        round_state = self._create_round_state()
        assert len(round_state.players[0].discards) == 0

        discard_tile(round_state, seat=0, tile_id=20)

        assert len(round_state.players[0].discards) == 1
        assert round_state.players[0].discards[0].tile_id == 20

    def test_discard_tile_returns_discard_object(self):
        round_state = self._create_round_state()

        result = discard_tile(round_state, seat=0, tile_id=20)

        assert isinstance(result, Discard)
        assert result.tile_id == 20

    def test_discard_tile_adds_to_all_discards(self):
        round_state = self._create_round_state()
        assert len(round_state.all_discards) == 0

        discard_tile(round_state, seat=0, tile_id=20)

        assert round_state.all_discards == [20]

    def test_discard_tile_raises_if_tile_not_in_hand(self):
        round_state = self._create_round_state()

        with pytest.raises(ValueError, match="tile 99 not in player's hand"):
            discard_tile(round_state, seat=0, tile_id=99)

    def test_discard_tile_sets_tsumogiri_for_last_tile(self):
        round_state = self._create_round_state()
        # last tile in hand (simulating just drawn)
        last_tile = round_state.players[0].tiles[-1]

        result = discard_tile(round_state, seat=0, tile_id=last_tile)

        assert result.is_tsumogiri is True

    def test_discard_tile_not_tsumogiri_for_other_tiles(self):
        round_state = self._create_round_state()
        # first tile in hand (not just drawn)
        first_tile = round_state.players[0].tiles[0]

        result = discard_tile(round_state, seat=0, tile_id=first_tile)

        assert result.is_tsumogiri is False

    def test_discard_tile_sets_riichi_flag(self):
        round_state = self._create_round_state()

        result = discard_tile(round_state, seat=0, tile_id=20, is_riichi=True)

        assert result.is_riichi_discard is True

    def test_discard_tile_clears_ippatsu_for_discarding_player_only(self):
        """Ippatsu is only cleared for the player who discards, not all players.

        Other players' ippatsu is cleared only on meld calls (pon/chi/kan).
        """
        round_state = self._create_round_state()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        round_state.players[2].is_ippatsu = True

        discard_tile(round_state, seat=0, tile_id=20)

        # discarding player's ippatsu is cleared
        assert round_state.players[0].is_ippatsu is False
        # other players' ippatsu is preserved (only cleared on meld calls)
        assert round_state.players[1].is_ippatsu is True
        assert round_state.players[2].is_ippatsu is True

    def test_discard_tile_clears_rinshan_flag(self):
        round_state = self._create_round_state()
        round_state.players[0].is_rinshan = True

        discard_tile(round_state, seat=0, tile_id=20)

        assert round_state.players[0].is_rinshan is False


class TestAdvanceTurn:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state for testing."""
        return MahjongRoundState(current_player_seat=0, turn_count=0)

    def test_advance_turn_rotates_seat(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 0

        advance_turn(round_state)

        assert round_state.current_player_seat == 1

    def test_advance_turn_wraps_around(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 3

        advance_turn(round_state)

        assert round_state.current_player_seat == 0

    def test_advance_turn_increments_turn_count(self):
        round_state = self._create_round_state()
        round_state.turn_count = 5

        advance_turn(round_state)

        assert round_state.turn_count == 6

    def test_advance_turn_returns_new_seat(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 1

        result = advance_turn(round_state)

        assert result == 2

    def test_advance_turn_full_rotation(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 0

        for expected_seat in [1, 2, 3, 0]:
            result = advance_turn(round_state)
            assert result == expected_seat


class TestCheckExhaustiveDraw:
    def test_returns_true_when_wall_empty(self):
        round_state = MahjongRoundState(wall=[])

        result = check_exhaustive_draw(round_state)

        assert result is True

    def test_returns_false_when_wall_has_tiles(self):
        round_state = MahjongRoundState(wall=[1, 2, 3])

        result = check_exhaustive_draw(round_state)

        assert result is False

    def test_returns_false_when_wall_has_one_tile(self):
        round_state = MahjongRoundState(wall=[42])

        result = check_exhaustive_draw(round_state)

        assert result is False


class TestIsTempai:
    def _create_tempai_hand(self) -> list[int]:
        """
        Create a tempai hand: 11m 234m 567m 888m, waiting for 9m pair.

        Tiles in 136-format:
        - 1m: tiles 0-3 (need 2)
        - 2m: tiles 4-7 (need 1)
        - 3m: tiles 8-11 (need 1)
        - 4m: tiles 12-15 (need 1)
        - 5m: tiles 16-19 (need 1)
        - 6m: tiles 20-23 (need 1)
        - 7m: tiles 24-27 (need 1)
        - 8m: tiles 28-31 (need 3)
        - 9m: tiles 32-35 (need 1 for wait)
        Total: 13 tiles
        """
        return [0, 1, 4, 8, 12, 16, 20, 24, 28, 29, 30, 32, 33]

    def _create_non_tempai_hand(self) -> list[int]:
        """
        Create a non-tempai hand (random disconnected tiles).

        13 tiles that don't form a near-complete hand.
        """
        # 1m 3m 5m 7m 9m 2p 4p 6p 8p 1s 3s 5s 7s
        return [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96]

    def test_is_tempai_returns_true_for_tempai_hand(self):
        player = MahjongPlayer(seat=0, name="Test", tiles=self._create_tempai_hand())

        result = is_tempai(player)

        assert result is True

    def test_is_tempai_returns_false_for_non_tempai_hand(self):
        player = MahjongPlayer(seat=0, name="Test", tiles=self._create_non_tempai_hand())

        result = is_tempai(player)

        assert result is False

    def test_is_tempai_with_chiitoi_wait(self):
        """
        Chiitoitsu (seven pairs) tempai: 6 pairs + 1 single tile.
        """
        # 11m 22m 33m 44m 55m 66m 7m (waiting for second 7m)
        hand = [0, 1, 4, 5, 8, 9, 12, 13, 16, 17, 20, 21, 24]
        player = MahjongPlayer(seat=0, name="Test", tiles=hand)

        result = is_tempai(player)

        assert result is True

    def test_is_tempai_with_open_hand(self):
        """
        Tempai with open hand (fewer tiles in hand due to melds).

        Player has 1 pon meld (3 tiles), so only 10 tiles in hand.
        """
        # hand: 234m 567m 888m 9m (10 tiles, waiting for 9m pair)
        hand = [4, 8, 12, 16, 20, 24, 28, 29, 30, 32]
        player = MahjongPlayer(seat=0, name="Test", tiles=hand)

        result = is_tempai(player)

        assert result is True


class TestProcessExhaustiveDraw:
    def _create_round_state_with_players(self, tempai_seats: list[int]) -> MahjongRoundState:
        """
        Create a round state with players where specified seats are in tempai.
        """
        players = []
        for seat in range(4):
            if seat in tempai_seats:
                # tempai hand: 11m 234m 567m 888m 9m
                tiles = [0, 1, 4, 8, 12, 16, 20, 24, 28, 29, 30, 32, 33]
            else:
                # non-tempai hand: disconnected tiles
                tiles = [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96]
            players.append(MahjongPlayer(seat=seat, name=f"Player{seat}", tiles=tiles, score=25000))
        return MahjongRoundState(players=players, wall=[])

    def test_process_exhaustive_draw_one_tempai(self):
        """
        1 tempai, 3 noten: each noten pays 1000 to tempai.
        """
        round_state = self._create_round_state_with_players(tempai_seats=[0])

        result = process_exhaustive_draw(round_state)

        assert result.tempai_seats == [0]
        assert result.noten_seats == [1, 2, 3]
        assert result.score_changes == {0: 3000, 1: -1000, 2: -1000, 3: -1000}
        # verify scores updated
        assert round_state.players[0].score == 28000
        assert round_state.players[1].score == 24000
        assert round_state.players[2].score == 24000
        assert round_state.players[3].score == 24000

    def test_process_exhaustive_draw_two_tempai(self):
        """
        2 tempai, 2 noten: each noten pays 1500 total, each tempai gets 1500.
        """
        round_state = self._create_round_state_with_players(tempai_seats=[0, 2])

        result = process_exhaustive_draw(round_state)

        assert result.tempai_seats == [0, 2]
        assert result.noten_seats == [1, 3]
        assert result.score_changes == {0: 1500, 1: -1500, 2: 1500, 3: -1500}
        assert round_state.players[0].score == 26500
        assert round_state.players[1].score == 23500
        assert round_state.players[2].score == 26500
        assert round_state.players[3].score == 23500

    def test_process_exhaustive_draw_three_tempai(self):
        """
        3 tempai, 1 noten: noten pays 1000 to each tempai.
        """
        round_state = self._create_round_state_with_players(tempai_seats=[0, 1, 2])

        result = process_exhaustive_draw(round_state)

        assert result.tempai_seats == [0, 1, 2]
        assert result.noten_seats == [3]
        assert result.score_changes == {0: 1000, 1: 1000, 2: 1000, 3: -3000}
        assert round_state.players[0].score == 26000
        assert round_state.players[1].score == 26000
        assert round_state.players[2].score == 26000
        assert round_state.players[3].score == 22000

    def test_process_exhaustive_draw_all_tempai(self):
        """
        All 4 tempai: no payment.
        """
        round_state = self._create_round_state_with_players(tempai_seats=[0, 1, 2, 3])

        result = process_exhaustive_draw(round_state)

        assert result.tempai_seats == [0, 1, 2, 3]
        assert result.noten_seats == []
        assert result.score_changes == {0: 0, 1: 0, 2: 0, 3: 0}
        for player in round_state.players:
            assert player.score == 25000

    def test_process_exhaustive_draw_all_noten(self):
        """
        All 4 noten: no payment.
        """
        round_state = self._create_round_state_with_players(tempai_seats=[])

        result = process_exhaustive_draw(round_state)

        assert result.tempai_seats == []
        assert result.noten_seats == [0, 1, 2, 3]
        assert result.score_changes == {0: 0, 1: 0, 2: 0, 3: 0}
        for player in round_state.players:
            assert player.score == 25000

    def test_process_exhaustive_draw_returns_type(self):
        """
        Verify the result dict contains the correct type field.
        """
        round_state = self._create_round_state_with_players(tempai_seats=[0])

        result = process_exhaustive_draw(round_state)

        assert result.type == "exhaustive_draw"
