"""
Unit tests for frozen Pydantic state models and state utilities.

Covers immutability contracts, FrozenMeld conversion boundaries,
state utility functions, and scoring integration.
Trivial Pydantic field-assignment/constructor tests removed.
"""

import pytest
from mahjong.meld import Meld
from mahjong.tile import TilesConverter
from pydantic import ValidationError

from game.logic.enums import CallType, GameAction, MeldCallType
from game.logic.meld_wrapper import FrozenMeld, frozen_melds_to_melds
from game.logic.scoring import calculate_hand_value
from game.logic.settings import GameSettings
from game.logic.state import (
    CallResponse,
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    add_discard_to_player,
    add_dora_indicator,
    add_prompt_response,
    add_tile_to_player,
    advance_turn,
    clear_all_players_ippatsu,
    clear_pending_prompt,
    pop_from_wall,
    remove_tile_from_player,
    update_all_discards,
    update_game_with_round,
    update_player,
)
from game.logic.types import MeldCaller
from game.logic.win import can_declare_tsumo


class TestImmutabilityContracts:
    """All frozen models reject attribute mutation."""

    def test_discard_rejects_mutation(self):
        discard = Discard(tile_id=0)
        with pytest.raises(ValidationError):
            discard.tile_id = 1

    def test_call_response_rejects_mutation(self):
        response = CallResponse(seat=1, action=GameAction.PASS)
        with pytest.raises(ValidationError):
            response.seat = 2

    def test_pending_call_prompt_rejects_mutation(self):
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        with pytest.raises(ValidationError):
            prompt.tile_id = 1

    def test_meld_caller_rejects_mutation(self):
        caller = MeldCaller(seat=1, call_type=MeldCallType.PON)
        with pytest.raises(ValidationError):
            caller.seat = 2

    def test_player_rejects_mutation(self):
        player = MahjongPlayer(seat=0, name="Player1", score=25000)
        with pytest.raises(ValidationError):
            player.score = 30000

    def test_round_state_rejects_mutation(self):
        state = MahjongRoundState()
        with pytest.raises(ValidationError):
            state.current_player_seat = 1

    def test_game_state_rejects_mutation(self):
        state = MahjongGameState()
        with pytest.raises(ValidationError):
            state.honba_sticks = 1

    def test_frozen_meld_rejects_mutation(self):
        meld = FrozenMeld(tiles=(0, 1, 2), meld_type=FrozenMeld.PON, opened=True)
        with pytest.raises(ValidationError):
            meld.tiles = (3, 4, 5)

    def test_model_copy_preserves_original_player(self):
        player = MahjongPlayer(seat=0, name="Player1", score=25000)
        new_player = player.model_copy(update={"score": 30000})
        assert player.score == 25000
        assert new_player.score == 30000

    def test_model_copy_preserves_original_round_state(self):
        state = MahjongRoundState(current_player_seat=0, turn_count=0)
        new_state = state.model_copy(update={"current_player_seat": 1, "turn_count": 1})
        assert state.current_player_seat == 0
        assert new_state.current_player_seat == 1


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


class TestGameStateDefaultFactory:
    def test_each_game_state_gets_unique_round_state(self):
        state1 = MahjongGameState()
        state2 = MahjongGameState()
        assert state1.round_state is not state2.round_state


class TestFrozenMeldConversion:
    def test_to_meld(self):
        frozen = FrozenMeld(
            tiles=(0, 1, 2),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=0,
            who=1,
            from_who=0,
        )
        meld = frozen.to_meld()
        assert meld.tiles == (0, 1, 2)
        assert meld.type == Meld.PON
        assert meld.opened is True
        assert meld.called_tile == 0
        assert meld.who == 1
        assert meld.from_who == 0


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
        with pytest.raises(ValueError, match="not in list"):
            remove_tile_from_player(state, 0, 999)


class TestStateUtilsWallOperations:
    def test_pop_from_wall_front(self):
        wall = tuple(range(10))
        state = MahjongRoundState(wall=wall)
        new_state, tile = pop_from_wall(state, from_front=True)

        assert tile == 0
        assert len(state.wall) == 10
        assert len(new_state.wall) == 9
        assert new_state.wall == tuple(range(1, 10))

    def test_pop_from_wall_back(self):
        wall = tuple(range(10))
        state = MahjongRoundState(wall=wall)
        new_state, tile = pop_from_wall(state, from_front=False)

        assert tile == 9
        assert len(new_state.wall) == 9
        assert new_state.wall == tuple(range(9))

    def test_pop_from_empty_wall_raises(self):
        state = MahjongRoundState(wall=())
        with pytest.raises(IndexError):
            pop_from_wall(state, from_front=True)


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
    def test_advance_turn(self):
        state = MahjongRoundState(current_player_seat=0, turn_count=0)
        new_state = advance_turn(state)

        assert state.current_player_seat == 0
        assert state.turn_count == 0
        assert new_state.current_player_seat == 1
        assert new_state.turn_count == 1

    def test_advance_turn_wraps_around(self):
        state = MahjongRoundState(current_player_seat=3, turn_count=10)
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


class TestStateUtilsGameStateUpdates:
    def test_update_game_with_round(self):
        round_state = MahjongRoundState(current_player_seat=2)
        game_state = MahjongGameState()
        new_game_state = update_game_with_round(game_state, round_state)

        assert game_state.round_state.current_player_seat == 0
        assert new_game_state.round_state.current_player_seat == 2


class TestStateUtilsDoraIndicators:
    def test_add_dora_indicator(self):
        state = MahjongRoundState(dora_indicators=(0,))
        new_state = add_dora_indicator(state, 4)

        assert state.dora_indicators == (0,)
        assert new_state.dora_indicators == (0, 4)


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
            wall=tuple(range(50)),
            dora_indicators=(0,),
            all_discards=(0, 1, 2, 3),
        )

        win_tile = closed_tiles[-1]
        result = calculate_hand_value(players[0], round_state, win_tile, GameSettings(), is_tsumo=True)

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
            wall=tuple(range(50)),
            dora_indicators=(0,),
            all_discards=(0, 1, 2, 3),
        )

        result = can_declare_tsumo(players[0], round_state, GameSettings())
        assert result is True
