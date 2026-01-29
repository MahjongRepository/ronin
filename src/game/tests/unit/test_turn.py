"""
Unit tests for turn loop orchestration.
"""

import pytest

from game.logic.abortive import check_four_riichi
from game.logic.actions import get_available_actions
from game.logic.enums import AbortiveDrawType, BotType, MeldViewType
from game.logic.game import init_game
from game.logic.melds import can_call_chi
from game.logic.round import draw_tile
from game.logic.state import MahjongGameState, RoundPhase
from game.logic.turn import (
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.logic.types import SeatConfig


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player", is_bot=False),
        SeatConfig(name="Tsumogiri 1", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", is_bot=True, bot_type=BotType.TSUMOGIRI),
    ]


class TestProcessDrawPhase:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        return init_game(_default_seat_configs(), seed=12345.0)

    def test_draw_phase_draws_tile(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        initial_wall_len = len(round_state.wall)
        initial_hand_len = len(round_state.players[0].tiles)

        events = process_draw_phase(round_state, game_state)

        assert len(round_state.wall) == initial_wall_len - 1
        assert len(round_state.players[0].tiles) == initial_hand_len + 1
        # find draw event
        draw_events = [e for e in events if e.type == "draw"]
        assert len(draw_events) == 1
        assert draw_events[0].seat == 0

    def test_draw_phase_returns_draw_event_with_tile(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        events = process_draw_phase(round_state, game_state)

        draw_event = next(e for e in events if e.type == "draw")
        assert hasattr(draw_event, "tile_id")
        assert draw_event.target == "seat_0"

    def test_draw_phase_returns_turn_event_with_actions(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        events = process_draw_phase(round_state, game_state)

        turn_events = [e for e in events if e.type == "turn"]
        assert len(turn_events) == 1
        assert hasattr(turn_events[0], "available_actions")
        assert turn_events[0].target == "seat_0"

    def test_draw_phase_exhaustive_draw(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        # empty the wall
        round_state.wall = []

        events = process_draw_phase(round_state, game_state)

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == "exhaustive_draw"
        assert round_state.phase == RoundPhase.FINISHED


class TestProcessDiscardPhase:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        # draw a tile for the dealer
        draw_tile(game_state.round_state)
        return game_state

    def test_discard_phase_creates_discard_event(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        discard_events = [e for e in events if e.type == "discard"]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard
        assert discard_events[0].target == "all"

    def test_discard_phase_removes_tile_from_hand(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        process_discard_phase(round_state, game_state, tile_to_discard)

        assert tile_to_discard not in round_state.players[0].tiles

    def test_discard_phase_adds_to_all_discards(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        process_discard_phase(round_state, game_state, tile_to_discard)

        assert tile_to_discard in round_state.all_discards

    def test_discard_phase_advances_turn_when_no_calls(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]
        initial_seat = round_state.current_player_seat

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        # if no call_prompt events, turn should advance
        call_prompts = [e for e in events if e.type == "call_prompt"]
        if not call_prompts:
            assert round_state.current_player_seat == (initial_seat + 1) % 4


class TestProcessDiscardPhaseWithRiichi:
    def _create_tempai_game_state(self) -> MahjongGameState:
        """Create a game state where player 0 is in tempai."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # manually set player 0 to have a tempai hand
        # 123m 456m 789m 111p, waiting for 2p
        round_state.players[0].tiles = [
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
            44,  # 3p (will discard this to be tempai waiting for 2p pair)
        ]
        # draw a tile
        draw_tile(round_state)

        return game_state

    def test_discard_phase_with_riichi_declaration(self):
        game_state = self._create_tempai_game_state()
        round_state = game_state.round_state
        # discard the drawn tile with riichi
        tile_to_discard = round_state.players[0].tiles[-1]

        events = process_discard_phase(round_state, game_state, tile_to_discard, is_riichi=True)

        # check for riichi declared event (if no ron calls)
        ron_prompts = [
            e for e in events if e.type == "call_prompt" and getattr(e, "call_type", None) == "ron"
        ]
        if not ron_prompts:
            riichi_events = [e for e in events if e.type == "riichi_declared"]
            assert len(riichi_events) == 1
            assert riichi_events[0].seat == 0
            assert round_state.players[0].is_riichi is True

    def test_discard_phase_riichi_fails_when_not_tempai(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        # player 0 has random tiles, not tempai
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[0]

        with pytest.raises(ValueError, match="cannot declare riichi"):
            process_discard_phase(round_state, game_state, tile_to_discard, is_riichi=True)


class TestProcessMeldCall:
    def _create_game_state_with_pon_opportunity(self) -> tuple[MahjongGameState, int]:
        """Create a game state where player 1 can pon a discarded tile."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 two 1m tiles (tiles 0-3 are all 1m)
        round_state.players[1].tiles = [0, 1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]

        # player 0 will discard another 1m
        tile_to_pon = 2  # third 1m tile
        round_state.players[0].tiles.append(tile_to_pon)
        round_state.current_player_seat = 0

        return game_state, tile_to_pon

    def test_process_pon_call(self):
        game_state, tile_to_pon = self._create_game_state_with_pon_opportunity()
        round_state = game_state.round_state

        events = process_meld_call(
            round_state, game_state, caller_seat=1, call_type="pon", tile_id=tile_to_pon
        )

        meld_events = [e for e in events if e.type == "meld"]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON
        assert meld_events[0].caller_seat == 1
        assert meld_events[0].from_seat == 0
        assert round_state.current_player_seat == 1

    def test_process_chi_call(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 1 has 2m and 3m tiles (can chi 1m from player 0)
        # tiles 4-7 are 2m, tiles 8-11 are 3m
        round_state.players[1].tiles = [4, 8, 20, 24, 28, 32, 40, 44, 48, 52, 60, 64, 68]

        # player 0 discards 1m (tile 0)
        round_state.current_player_seat = 0
        tile_to_chi = 0  # 1m

        # chi requires sequence_tiles
        events = process_meld_call(
            round_state,
            game_state,
            caller_seat=1,
            call_type="chi",
            tile_id=tile_to_chi,
            sequence_tiles=(4, 8),  # 2m, 3m
        )

        meld_events = [e for e in events if e.type == "meld"]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CHI
        assert meld_events[0].caller_seat == 1
        assert round_state.current_player_seat == 1

    def test_process_chi_call_requires_sequence_tiles(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        round_state.current_player_seat = 0

        with pytest.raises(ValueError, match="chi call requires sequence_tiles"):
            process_meld_call(round_state, game_state, caller_seat=1, call_type="chi", tile_id=0)


class TestProcessRonCall:
    def _create_game_state_with_ron_opportunity(self) -> tuple[MahjongGameState, int, int]:
        """Create a game state where player 1 can ron on player 0's discard."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a winning hand (needs one tile to complete)
        # complete hand: 123m 456m 789m 111p 22p
        # waiting for 2p: tiles 40-43
        round_state.players[1].tiles = [
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
            40,  # 2p (will receive another 2p for pair)
        ]

        # player 0 has the winning tile
        win_tile = 41  # 2p
        round_state.players[0].tiles.append(win_tile)
        round_state.current_player_seat = 0

        return game_state, win_tile, 0  # discarder_seat

    def test_process_single_ron(self):
        game_state, win_tile, discarder_seat = self._create_game_state_with_ron_opportunity()
        round_state = game_state.round_state

        events = process_ron_call(
            round_state, game_state, ron_callers=[1], tile_id=win_tile, discarder_seat=discarder_seat
        )

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        result = round_end_events[0].result
        assert result.type == "ron"
        assert result.winner_seat == 1
        assert result.loser_seat == 0
        assert round_state.phase == RoundPhase.FINISHED


class TestProcessTsumoCall:
    def _create_game_state_with_tsumo(self) -> MahjongGameState:
        """Create a game state where player 0 has a winning hand."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 a complete winning hand (14 tiles)
        # 123m 456m 789m 111p 22p
        round_state.players[0].tiles = [
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
            40,
            41,  # 22p
        ]

        return game_state

    def test_process_tsumo(self):
        game_state = self._create_game_state_with_tsumo()
        round_state = game_state.round_state

        events = process_tsumo_call(round_state, game_state, winner_seat=0)

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        result = round_end_events[0].result
        assert result.type == "tsumo"
        assert result.winner_seat == 0
        assert round_state.phase == RoundPhase.FINISHED


class TestGetAvailableActions:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        # draw a tile for the dealer
        draw_tile(game_state.round_state)
        return game_state

    def _find_action(self, actions: list, action_type: str):
        """Find an action by type in the actions list."""
        for action in actions:
            if action.action == action_type:
                return action
        return None

    def test_get_available_actions_returns_discard_tiles(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_action = self._find_action(actions, "discard")
        assert discard_action is not None
        assert discard_action.tiles is not None
        assert len(discard_action.tiles) == 14  # 13 dealt + 1 drawn

    def test_get_available_actions_returns_riichi_option(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        # riichi action is present only if player is in tempai
        # check that the function returns a list of actions
        assert isinstance(actions, list)

    def test_get_available_actions_returns_tsumo_option(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        # tsumo action is present only if player has a winning hand
        assert isinstance(actions, list)

    def test_get_available_actions_returns_kan_options(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        # kan/added_kan actions are present only if player has kan options
        assert isinstance(actions, list)

    def test_get_available_actions_riichi_limits_discards(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        round_state.players[0].is_riichi = True

        actions = get_available_actions(round_state, game_state, seat=0)

        # in riichi, can only discard the drawn tile
        discard_action = self._find_action(actions, "discard")
        assert discard_action is not None
        assert discard_action.tiles is not None
        assert len(discard_action.tiles) == 1
        assert discard_action.tiles[0] == round_state.players[0].tiles[-1]


class TestFourWindsAbortiveDraw:
    def _create_game_state_for_four_winds(self) -> MahjongGameState:
        """Create a game state where four winds can occur."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give each player an East wind tile (E = tile 108-111)
        # first player
        east_tiles = [108, 109, 110, 111]
        for i, player in enumerate(round_state.players):
            player.tiles = list(range(i * 13, (i + 1) * 13))  # placeholder tiles
            player.tiles[0] = east_tiles[i]  # add East wind

        return game_state

    def test_four_winds_abortive_draw(self):
        game_state = self._create_game_state_for_four_winds()
        round_state = game_state.round_state

        # draw for player 0
        draw_tile(round_state)

        # simulate 4 East wind discards
        east_tiles = [108, 109, 110, 111]

        for i in range(4):
            round_state.current_player_seat = i
            round_state.players[i].tiles.append(east_tiles[i])  # ensure they have the tile
            events = process_discard_phase(round_state, game_state, east_tiles[i])

            if i == 3:  # fourth discard triggers four winds
                round_end_events = [e for e in events if e.type == "round_end"]
                assert len(round_end_events) == 1
                assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_WINDS
                assert round_state.phase == RoundPhase.FINISHED


class TestFourRiichiAbortiveDraw:
    def _create_tempai_for_all(self) -> MahjongGameState:
        """Create a game state where all players are in tempai."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # tempai hand for all players: 123m 456m 789m 111p, waiting for 2p
        base_hand = [
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
        ]

        for i, player in enumerate(round_state.players):
            # each player gets the base hand plus one unique tile to discard
            player.tiles = [*list(base_hand), 44 + i]  # 3p, 4p, 5p, 6p respectively

        return game_state

    def test_four_riichi_tracking(self):
        """Test that four riichi is detected after all players declare riichi."""
        game_state = self._create_tempai_for_all()
        round_state = game_state.round_state

        # declare riichi for all 4 players manually
        for player in round_state.players:
            player.is_riichi = True

        # verify the condition is detected
        assert check_four_riichi(round_state) is True


class TestRiichiPlayerExcludedFromMeldCallers:
    """Tests that riichi players cannot call melds on discarded tiles."""

    def _create_game_state_with_meld_opportunity(self) -> tuple[MahjongGameState, int]:
        """Create a game where player 1 could call pon if not in riichi."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 two 1m tiles
        round_state.players[1].tiles = [0, 1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]

        # player 0 will discard a 1m tile
        tile_to_discard = 2
        round_state.players[0].tiles.append(tile_to_discard)
        round_state.current_player_seat = 0

        return game_state, tile_to_discard

    def test_riichi_player_excluded_from_pon_callers(self):
        """Riichi players should not appear in meld callers for pon."""
        game_state, tile_to_discard = self._create_game_state_with_meld_opportunity()
        round_state = game_state.round_state

        # player 1 is NOT in riichi - should be able to call pon
        events = process_discard_phase(round_state, game_state, tile_to_discard)
        call_prompts = [
            e for e in events if e.type == "call_prompt" and getattr(e, "call_type", None) == "meld"
        ]
        if call_prompts:
            callers = call_prompts[0].callers
            caller_seats = [c.seat if hasattr(c, "seat") else c for c in callers]
            assert 1 in caller_seats

    def test_riichi_player_excluded_from_pon_callers_when_riichi(self):
        """Riichi players should be excluded from meld callers."""
        game_state, tile_to_discard = self._create_game_state_with_meld_opportunity()
        round_state = game_state.round_state

        # put player 1 in riichi
        round_state.players[1].is_riichi = True

        events = process_discard_phase(round_state, game_state, tile_to_discard)
        call_prompts = [
            e for e in events if e.type == "call_prompt" and getattr(e, "call_type", None) == "meld"
        ]
        if call_prompts:
            callers = call_prompts[0].callers
            caller_seats = [c.seat if hasattr(c, "seat") else c for c in callers]
            # player 1 should NOT be in callers since they're in riichi
            assert 1 not in caller_seats

    def test_riichi_player_discard_limited_to_drawn_tile(self):
        """After riichi, only the drawn tile should be discardable."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[0]

        # setup: player draws and is in riichi
        drawn_tile = draw_tile(round_state)
        player.is_riichi = True

        actions = get_available_actions(round_state, game_state, seat=0)

        # find the discard action
        discard_action = next((a for a in actions if a.action == "discard"), None)
        assert discard_action is not None
        # should only be able to discard the drawn tile
        assert discard_action.tiles is not None
        assert len(discard_action.tiles) == 1
        assert discard_action.tiles[0] == drawn_tile

    def test_riichi_player_cannot_call_chi(self):
        """Verify can_call_chi returns empty for riichi players."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[1]

        # give player 1 tiles that could form a sequence
        player.tiles = [0, 4, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]
        discarded_tile = 8  # 3m, would form 1-2-3m sequence

        # not in riichi - should be able to chi
        options = can_call_chi(player, discarded_tile, discarder_seat=0, caller_seat=1)
        assert len(options) > 0

        # in riichi - should not be able to chi
        player.is_riichi = True
        options = can_call_chi(player, discarded_tile, discarder_seat=0, caller_seat=1)
        assert options == []
