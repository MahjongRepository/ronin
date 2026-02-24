"""
Unit tests for FrozenMeld conversion boundaries,
state utility functions, and scoring integration.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import CallType, GameAction, WindName
from game.logic.meld_wrapper import FrozenMeld, frozen_melds_to_melds
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings
from game.logic.state import (
    CallResponse,
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    PendingCallPrompt,
    get_player_view,
    wind_name,
)
from game.logic.state_utils import (
    add_discard_to_player,
    add_prompt_response,
    add_tile_to_player,
    advance_turn,
    clear_all_players_ippatsu,
    clear_pending_prompt,
    remove_tile_from_player,
    update_all_discards,
    update_player,
)
from game.logic.wall import Wall
from game.logic.win import can_declare_tsumo


class TestMahjongPlayerLogic:
    def test_has_open_melds_with_open(self):
        open_meld = FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True)
        player = MahjongPlayer(seat=0, name="P1", melds=(open_meld,), score=25000)
        assert player.has_open_melds() is True

    def test_has_open_melds_with_closed(self):
        closed_meld = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=False)
        player = MahjongPlayer(seat=0, name="P2", melds=(closed_meld,), score=25000)
        assert player.has_open_melds() is False

    def test_has_open_melds_empty(self):
        player = MahjongPlayer(seat=0, name="P3", score=25000)
        assert player.has_open_melds() is False


class TestFrozenMeldsToMeldsFunction:
    def test_empty_tuple_returns_none(self):
        assert frozen_melds_to_melds(()) is None

    def test_none_returns_none(self):
        assert frozen_melds_to_melds(None) is None


class TestStateUtilsUpdatePlayer:
    def _create_round_state_with_players(self) -> MahjongRoundState:
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        return MahjongRoundState(players=players)

    def test_update_player_score(self):
        state = self._create_round_state_with_players()
        new_state = update_player(state, 0, score=30000)

        assert state.players[0].score == 25000
        assert new_state.players[0].score == 30000
        assert new_state.players[1].score == 25000

    def test_update_player_multiple_fields(self):
        state = self._create_round_state_with_players()
        new_state = update_player(state, 1, is_riichi=True, is_ippatsu=True, score=24000)

        assert new_state.players[1].is_riichi is True
        assert new_state.players[1].is_ippatsu is True
        assert new_state.players[1].score == 24000


class TestStateUtilsTileOperations:
    def _create_round_state_with_tiles(self) -> MahjongRoundState:
        tiles = tuple(TilesConverter.string_to_136_array(man="123456789"))
        player = MahjongPlayer(seat=0, name="Player0", tiles=tiles, score=25000)
        players = (player, *tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(1, 4)))
        return MahjongRoundState(players=players)

    def test_add_tile_to_player(self):
        state = self._create_round_state_with_tiles()
        new_tile = TilesConverter.string_to_136_array(pin="1")[0]
        new_state = add_tile_to_player(state, 0, new_tile)

        assert len(state.players[0].tiles) == 9
        assert len(new_state.players[0].tiles) == 10
        assert new_state.players[0].tiles[-1] == new_tile

    def test_remove_tile_from_player(self):
        state = self._create_round_state_with_tiles()
        tile_to_remove = state.players[0].tiles[0]
        new_state = remove_tile_from_player(state, 0, tile_to_remove)

        assert len(state.players[0].tiles) == 9
        assert len(new_state.players[0].tiles) == 8
        assert tile_to_remove not in new_state.players[0].tiles

    def test_remove_tile_not_in_hand_raises(self):
        state = self._create_round_state_with_tiles()
        with pytest.raises(ValueError, match="Tile 999 not in hand of player at seat 0"):
            remove_tile_from_player(state, 0, 999)


class TestStateUtilsDiscardOperations:
    def test_add_discard_to_player(self):
        player = MahjongPlayer(seat=0, name="Player0", score=25000)
        state = MahjongRoundState(players=(player,))

        discard = Discard(tile_id=0, is_tsumogiri=True)
        new_state = add_discard_to_player(state, 0, discard)

        assert len(state.players[0].discards) == 0
        assert len(new_state.players[0].discards) == 1
        assert new_state.players[0].discards[0] == discard

    def test_update_all_discards(self):
        state = MahjongRoundState(all_discards=(1, 2, 3))
        new_state = update_all_discards(state, 4)

        assert state.all_discards == (1, 2, 3)
        assert new_state.all_discards == (1, 2, 3, 4)


class TestStateUtilsTurnAdvance:
    def _players(self) -> tuple[MahjongPlayer, ...]:
        return tuple(MahjongPlayer(seat=i, name=f"P{i}", score=25000) for i in range(4))

    def test_advance_turn(self):
        state = MahjongRoundState(players=self._players(), current_player_seat=0, turn_count=0)
        new_state = advance_turn(state)

        assert state.current_player_seat == 0
        assert state.turn_count == 0
        assert new_state.current_player_seat == 1
        assert new_state.turn_count == 1

    def test_wraps_around_to_seat_zero(self):
        state = MahjongRoundState(players=self._players(), current_player_seat=3, turn_count=10)
        new_state = advance_turn(state)
        assert new_state.current_player_seat == 0
        assert new_state.turn_count == 11


class TestStateUtilsPendingPrompt:
    def test_clear_pending_prompt(self):
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        state = MahjongRoundState(pending_call_prompt=prompt)
        new_state = clear_pending_prompt(state)

        assert state.pending_call_prompt is not None
        assert new_state.pending_call_prompt is None

    def test_add_prompt_response(self):
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(1, 2),
        )
        response = CallResponse(seat=1, action=GameAction.PASS)
        new_prompt = add_prompt_response(prompt, response)

        assert len(prompt.responses) == 0
        assert prompt.pending_seats == frozenset({1, 2})
        assert len(new_prompt.responses) == 1
        assert new_prompt.pending_seats == frozenset({2})

    def test_add_prompt_response_rejects_seat_not_in_pending(self):
        """Raises KeyError when response seat is not in pending_seats."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        response = CallResponse(seat=3, action=GameAction.PASS)
        with pytest.raises(KeyError):
            add_prompt_response(prompt, response)


class TestStateUtilsPlayerFlags:
    def test_clear_all_players_ippatsu(self):
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                is_ippatsu=(i in {0, 2}),
                score=25000,
            )
            for i in range(4)
        )
        state = MahjongRoundState(players=players)
        new_state = clear_all_players_ippatsu(state)

        assert state.players[0].is_ippatsu is True
        for i in range(4):
            assert new_state.players[i].is_ippatsu is False

    def test_clear_all_players_ippatsu_returns_same_state_when_none_set(self):
        """Short-circuits and returns the same state object when no ippatsu flags are set."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", is_ippatsu=False, score=25000) for i in range(4))
        state = MahjongRoundState(players=players)
        new_state = clear_all_players_ippatsu(state)

        assert new_state is state


class TestFrozenMeldScoringIntegration:
    def test_scoring_with_frozen_meld(self):
        """calculate_hand_value works with FrozenMeld from frozen player."""
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        frozen_meld = FrozenMeld(
            tiles=tuple(haku_tiles),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        discard1 = Discard(tile_id=0, is_tsumogiri=False)

        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                tiles=tuple(closed_tiles) if i == 0 else (),
                melds=(frozen_meld,) if i == 0 else (),
                discards=(discard1,),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            wall=Wall(live_tiles=tuple(range(50)), dora_indicators=(0,)),
            all_discards=(0, 1, 2, 3),
        )

        win_tile = closed_tiles[-1]
        ctx = ScoringContext(player=players[0], round_state=round_state, settings=GameSettings(), is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han >= 1

    def test_can_declare_tsumo_with_frozen_meld(self):
        """can_declare_tsumo works with FrozenMeld from frozen player."""
        tenpai_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        frozen_meld = FrozenMeld(
            tiles=tuple(haku_tiles),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        discard1 = Discard(tile_id=0, is_tsumogiri=False)

        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                tiles=tuple(tenpai_tiles) if i == 0 else (),
                melds=(frozen_meld,) if i == 0 else (),
                discards=(discard1,),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            wall=Wall(live_tiles=tuple(range(50)), dora_indicators=(0,)),
            all_discards=(0, 1, 2, 3),
        )

        result = can_declare_tsumo(players[0], round_state, GameSettings())
        assert result is True


class TestUpdatePlayerValidation:
    """Tests for update_player seat bounds and field name validation."""

    def _create_round_state(self) -> MahjongRoundState:
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        return MahjongRoundState(players=players)

    def test_rejects_negative_seat(self):
        state = self._create_round_state()
        with pytest.raises(ValueError, match="Invalid seat -1"):
            update_player(state, -1, score=30000)

    def test_rejects_out_of_bounds_seat(self):
        state = self._create_round_state()
        with pytest.raises(ValueError, match="Invalid seat 4"):
            update_player(state, 4, score=30000)

    def test_rejects_invalid_field_name(self):
        state = self._create_round_state()
        with pytest.raises(ValueError, match="Invalid player fields"):
            update_player(state, 0, nonexistent_field=True)


class TestGetPlayerViewValidation:
    """Tests for get_player_view seat validation."""

    def test_rejects_invalid_seat(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(players=players)
        game_state = MahjongGameState(round_state=round_state)

        with pytest.raises(ValueError, match="No player found at seat 5"):
            get_player_view(game_state, 5)

    def test_valid_seat_returns_view(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", tiles=(i,), score=25000) for i in range(4))
        round_state = MahjongRoundState(players=players)
        game_state = MahjongGameState(round_state=round_state)

        view = get_player_view(game_state, 2)
        assert view.seat == 2
        assert view.my_tiles == [2]


class TestWindNameConstant:
    """Test wind_name uses module-level constant."""

    def test_all_winds(self):
        assert wind_name(0) == WindName.EAST
        assert wind_name(1) == WindName.SOUTH
        assert wind_name(2) == WindName.WEST
        assert wind_name(3) == WindName.NORTH

    def test_out_of_range_returns_unknown(self):
        assert wind_name(-1) == WindName.UNKNOWN
        assert wind_name(4) == WindName.UNKNOWN
        assert wind_name(100) == WindName.UNKNOWN
