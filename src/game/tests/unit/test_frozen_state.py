"""
Unit tests for frozen Pydantic state models and state utilities.
"""

import pytest
from mahjong.meld import Meld
from mahjong.tile import TilesConverter
from pydantic import ValidationError

from game.logic.enums import CallType, GameAction, GamePhase, MeldCallType, RoundPhase
from game.logic.meld_wrapper import FrozenMeld, frozen_melds_to_melds
from game.logic.scoring import calculate_hand_value
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
    clear_player_flags,
    pop_from_wall,
    remove_tile_from_player,
    update_all_discards,
    update_current_player,
    update_game_with_round,
    update_player,
    update_round_phase,
)
from game.logic.types import MeldCaller
from game.logic.win import can_declare_tsumo


class TestDiscard:
    def test_create_basic_discard(self):
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        discard = Discard(tile_id=man_1m)
        assert discard.tile_id == man_1m
        assert discard.is_tsumogiri is False
        assert discard.is_riichi_discard is False

    def test_create_tsumogiri_discard(self):
        pin_1p = TilesConverter.string_to_136_array(pin="1")[0]
        discard = Discard(tile_id=pin_1p, is_tsumogiri=True)
        assert discard.tile_id == pin_1p
        assert discard.is_tsumogiri is True

    def test_create_riichi_discard(self):
        sou_1s = TilesConverter.string_to_136_array(sou="1")[0]
        discard = Discard(tile_id=sou_1s, is_riichi_discard=True)
        assert discard.tile_id == sou_1s
        assert discard.is_riichi_discard is True

    def test_frozen_discard_is_immutable(self):
        discard = Discard(tile_id=0)
        with pytest.raises(ValidationError):
            discard.tile_id = 1


class TestCallResponse:
    def test_create_call_response(self):
        response = CallResponse(seat=1, action=GameAction.CALL_PON)
        assert response.seat == 1
        assert response.action == GameAction.CALL_PON
        assert response.sequence_tiles is None

    def test_create_chi_response_with_sequence(self):
        response = CallResponse(
            seat=2,
            action=GameAction.CALL_CHI,
            sequence_tiles=(4, 8),
        )
        assert response.seat == 2
        assert response.action == GameAction.CALL_CHI
        assert response.sequence_tiles == (4, 8)

    def test_frozen_call_response_is_immutable(self):
        response = CallResponse(seat=1, action=GameAction.PASS)
        with pytest.raises(ValidationError):
            response.seat = 2


class TestPendingCallPrompt:
    def test_create_pending_call_prompt(self):
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1, 2, 3}),
            callers=(1, 2, 3),
        )
        assert prompt.call_type == CallType.MELD
        assert prompt.tile_id == 0
        assert prompt.from_seat == 0
        assert prompt.pending_seats == frozenset({1, 2, 3})
        assert prompt.callers == (1, 2, 3)
        assert prompt.responses == ()

    def test_create_prompt_with_meld_callers(self):
        caller = MeldCaller(
            seat=1,
            call_type=MeldCallType.CHI,
            options=((4, 8), (8, 12)),
        )
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(caller,),
        )
        assert len(prompt.callers) == 1
        assert isinstance(prompt.callers[0], MeldCaller)

    def test_frozen_pending_call_prompt_is_immutable(self):
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        with pytest.raises(ValidationError):
            prompt.tile_id = 1


class TestMeldCallerImmutability:
    def test_create_basic_meld_caller(self):
        caller = MeldCaller(seat=1, call_type=MeldCallType.PON)
        assert caller.seat == 1
        assert caller.call_type == MeldCallType.PON
        assert caller.options is None

    def test_create_chi_caller_with_options(self):
        caller = MeldCaller(
            seat=1,
            call_type=MeldCallType.CHI,
            options=((0, 4), (4, 8)),
        )
        assert caller.options == ((0, 4), (4, 8))

    def test_frozen_meld_caller_is_immutable(self):
        caller = MeldCaller(seat=1, call_type=MeldCallType.PON)
        with pytest.raises(ValidationError):
            caller.seat = 2

    def test_meld_caller_preserves_none_options(self):
        """Test that None options are preserved."""
        caller = MeldCaller(
            seat=1,
            call_type=MeldCallType.PON,
            options=None,
        )
        assert caller.options is None


class TestMahjongPlayer:
    def test_create_default_player(self):
        player = MahjongPlayer(seat=0, name="Player1")
        assert player.seat == 0
        assert player.name == "Player1"
        assert player.tiles == ()
        assert player.discards == ()
        assert player.melds == ()
        assert player.is_riichi is False
        assert player.is_ippatsu is False
        assert player.is_daburi is False
        assert player.is_rinshan is False
        assert player.kuikae_tiles == ()
        assert player.pao_seat is None
        assert player.is_temporary_furiten is False
        assert player.is_riichi_furiten is False
        assert player.score == 25000

    def test_create_player_with_tiles(self):
        tiles = tuple(TilesConverter.string_to_136_array(man="123", pin="123", sou="123", honors="1115"))
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert player.tiles == tiles
        assert len(player.tiles) == 13

    def test_create_player_with_melds(self):
        meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
        )
        player = MahjongPlayer(seat=0, name="Player1", melds=(meld,))
        assert len(player.melds) == 1
        assert player.melds[0].type == FrozenMeld.PON

    def test_player_has_open_melds(self):
        open_meld = FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True)
        closed_meld = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=False)

        player_with_open = MahjongPlayer(seat=0, name="P1", melds=(open_meld,))
        assert player_with_open.has_open_melds() is True

        player_with_closed = MahjongPlayer(seat=0, name="P2", melds=(closed_meld,))
        assert player_with_closed.has_open_melds() is False

        player_no_melds = MahjongPlayer(seat=0, name="P3")
        assert player_no_melds.has_open_melds() is False

    def test_frozen_player_is_immutable(self):
        player = MahjongPlayer(seat=0, name="Player1")
        with pytest.raises(ValidationError):
            player.score = 30000

    def test_model_copy_creates_new_instance(self):
        player = MahjongPlayer(seat=0, name="Player1", score=25000)
        new_player = player.model_copy(update={"score": 30000})
        assert player.score == 25000  # original unchanged
        assert new_player.score == 30000  # copy updated


class TestMahjongRoundState:
    def test_create_default_round_state(self):
        state = MahjongRoundState()
        assert state.wall == ()
        assert state.dead_wall == ()
        assert state.dora_indicators == ()
        assert state.players == ()
        assert state.dealer_seat == 0
        assert state.current_player_seat == 0
        assert state.round_wind == 0
        assert state.turn_count == 0
        assert state.all_discards == ()
        assert state.players_with_open_hands == ()
        assert state.pending_dora_count == 0
        assert state.phase == RoundPhase.WAITING
        assert state.pending_call_prompt is None

    def test_create_round_state_with_wall(self):
        wall = tuple(range(122))
        state = MahjongRoundState(wall=wall)
        assert len(state.wall) == 122

    def test_create_round_state_with_players(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        state = MahjongRoundState(players=players)
        assert len(state.players) == 4

    def test_frozen_round_state_is_immutable(self):
        state = MahjongRoundState()
        with pytest.raises(ValidationError):
            state.current_player_seat = 1

    def test_model_copy_creates_new_instance(self):
        state = MahjongRoundState(current_player_seat=0, turn_count=0)
        new_state = state.model_copy(update={"current_player_seat": 1, "turn_count": 1})
        assert state.current_player_seat == 0  # original unchanged
        assert new_state.current_player_seat == 1  # copy updated


class TestMahjongGameState:
    def test_create_default_game_state(self):
        state = MahjongGameState()
        assert state.round_state is not None
        assert state.round_number == 0
        assert state.unique_dealers == 1
        assert state.honba_sticks == 0
        assert state.riichi_sticks == 0
        assert state.game_phase == GamePhase.IN_PROGRESS
        assert state.seed == 0.0

    def test_create_game_state_with_custom_values(self):
        state = MahjongGameState(
            round_number=4,
            unique_dealers=5,
            honba_sticks=2,
            riichi_sticks=3,
            seed=12345.0,
        )
        assert state.round_number == 4
        assert state.unique_dealers == 5
        assert state.honba_sticks == 2
        assert state.riichi_sticks == 3
        assert state.seed == 12345.0

    def test_create_game_state_with_round_state(self):
        round_state = MahjongRoundState(dealer_seat=2, round_wind=1)
        state = MahjongGameState(round_state=round_state)
        assert state.round_state.dealer_seat == 2
        assert state.round_state.round_wind == 1

    def test_frozen_game_state_is_immutable(self):
        state = MahjongGameState()
        with pytest.raises(ValidationError):
            state.honba_sticks = 1

    def test_each_game_state_gets_unique_round_state(self):
        state1 = MahjongGameState()
        state2 = MahjongGameState()
        # Each should have their own round_state instance (via default_factory)
        assert state1.round_state is not state2.round_state


class TestStateUtilsUpdatePlayer:
    def _create_round_state_with_players(self) -> MahjongRoundState:
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        return MahjongRoundState(players=players)

    def test_update_player_score(self):
        state = self._create_round_state_with_players()
        new_state = update_player(state, 0, score=30000)

        assert state.players[0].score == 25000  # original unchanged
        assert new_state.players[0].score == 30000  # updated
        assert new_state.players[1].score == 25000  # others unchanged

    def test_update_player_multiple_fields(self):
        state = self._create_round_state_with_players()
        new_state = update_player(state, 1, is_riichi=True, is_ippatsu=True, score=24000)

        assert new_state.players[1].is_riichi is True
        assert new_state.players[1].is_ippatsu is True
        assert new_state.players[1].score == 24000

    def test_update_current_player(self):
        state = self._create_round_state_with_players()
        state = state.model_copy(update={"current_player_seat": 2})
        new_state = update_current_player(state, is_riichi=True)

        assert new_state.players[2].is_riichi is True
        assert new_state.players[0].is_riichi is False


class TestStateUtilsTileOperations:
    def _create_round_state_with_tiles(self) -> MahjongRoundState:
        tiles = tuple(TilesConverter.string_to_136_array(man="123456789"))
        player = MahjongPlayer(seat=0, name="Player0", tiles=tiles)
        players = (player, *tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(1, 4)))
        return MahjongRoundState(players=players)

    def test_add_tile_to_player(self):
        state = self._create_round_state_with_tiles()
        new_tile = TilesConverter.string_to_136_array(pin="1")[0]
        new_state = add_tile_to_player(state, 0, new_tile)

        assert len(state.players[0].tiles) == 9  # original unchanged
        assert len(new_state.players[0].tiles) == 10  # tile added
        assert new_state.players[0].tiles[-1] == new_tile

    def test_remove_tile_from_player(self):
        state = self._create_round_state_with_tiles()
        tile_to_remove = state.players[0].tiles[0]
        new_state = remove_tile_from_player(state, 0, tile_to_remove)

        assert len(state.players[0].tiles) == 9  # original unchanged
        assert len(new_state.players[0].tiles) == 8  # tile removed
        assert tile_to_remove not in new_state.players[0].tiles

    def test_remove_tile_not_in_hand_raises(self):
        state = self._create_round_state_with_tiles()
        non_existent_tile = 999
        with pytest.raises(ValueError, match="not in list"):
            remove_tile_from_player(state, 0, non_existent_tile)


class TestStateUtilsWallOperations:
    def test_pop_from_wall_front(self):
        wall = tuple(range(10))
        state = MahjongRoundState(wall=wall)
        new_state, tile = pop_from_wall(state, from_front=True)

        assert tile == 0
        assert len(state.wall) == 10  # original unchanged
        assert len(new_state.wall) == 9  # tile removed
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
        player = MahjongPlayer(seat=0, name="Player0")
        state = MahjongRoundState(players=(player,))

        discard = Discard(tile_id=0, is_tsumogiri=True)
        new_state = add_discard_to_player(state, 0, discard)

        assert len(state.players[0].discards) == 0  # original unchanged
        assert len(new_state.players[0].discards) == 1  # discard added
        assert new_state.players[0].discards[0] == discard

    def test_update_all_discards(self):
        state = MahjongRoundState(all_discards=(1, 2, 3))
        new_state = update_all_discards(state, 4)

        assert state.all_discards == (1, 2, 3)  # original unchanged
        assert new_state.all_discards == (1, 2, 3, 4)


class TestStateUtilsTurnAdvance:
    def test_advance_turn(self):
        state = MahjongRoundState(current_player_seat=0, turn_count=0)
        new_state = advance_turn(state)

        assert state.current_player_seat == 0  # original unchanged
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

        assert state.pending_call_prompt is not None  # original unchanged
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

        assert len(prompt.responses) == 0  # original unchanged
        assert prompt.pending_seats == frozenset({1, 2})
        assert len(new_prompt.responses) == 1  # response added
        assert new_prompt.pending_seats == frozenset({2})  # seat removed


class TestStateUtilsGameStateUpdates:
    def test_update_game_with_round(self):
        round_state = MahjongRoundState(current_player_seat=2)
        game_state = MahjongGameState()
        new_game_state = update_game_with_round(game_state, round_state)

        assert game_state.round_state.current_player_seat == 0  # original unchanged
        assert new_game_state.round_state.current_player_seat == 2

    def test_update_round_phase(self):
        state = MahjongRoundState(phase=RoundPhase.WAITING)
        new_state = update_round_phase(state, RoundPhase.PLAYING)

        assert state.phase == RoundPhase.WAITING  # original unchanged
        assert new_state.phase == RoundPhase.PLAYING


class TestStateUtilsDoraIndicators:
    def test_add_dora_indicator(self):
        state = MahjongRoundState(dora_indicators=(0,))
        new_state = add_dora_indicator(state, 4)

        assert state.dora_indicators == (0,)  # original unchanged
        assert new_state.dora_indicators == (0, 4)


class TestStateUtilsPlayerFlags:
    def test_clear_player_flags(self):
        player = MahjongPlayer(
            seat=0,
            name="Player0",
            is_ippatsu=True,
            is_temporary_furiten=True,
            is_rinshan=True,
            kuikae_tiles=(0, 1),
        )
        state = MahjongRoundState(players=(player,))
        new_state = clear_player_flags(state, 0)

        assert state.players[0].is_ippatsu is True  # original unchanged
        assert new_state.players[0].is_ippatsu is False
        assert new_state.players[0].is_temporary_furiten is False
        assert new_state.players[0].is_rinshan is False
        assert new_state.players[0].kuikae_tiles == ()

    def test_clear_all_players_ippatsu(self):
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                is_ippatsu=(i in {0, 2}),  # players 0 and 2 have ippatsu
            )
            for i in range(4)
        )
        state = MahjongRoundState(players=players)
        new_state = clear_all_players_ippatsu(state)

        assert state.players[0].is_ippatsu is True  # original unchanged
        for i in range(4):
            assert new_state.players[i].is_ippatsu is False


class TestFrozenMeld:
    def test_create_frozen_meld(self):
        meld = FrozenMeld(
            tiles=(0, 1, 2),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=0,
            who=1,
            from_who=0,
        )
        assert meld.tiles == (0, 1, 2)
        assert meld.meld_type == FrozenMeld.PON
        assert meld.type == FrozenMeld.PON
        assert meld.opened is True
        assert meld.called_tile == 0
        assert meld.who == 1
        assert meld.from_who == 0

    def test_frozen_meld_is_immutable(self):
        meld = FrozenMeld(
            tiles=(0, 1, 2),
            meld_type=FrozenMeld.PON,
            opened=True,
        )
        with pytest.raises(ValidationError):
            meld.tiles = (3, 4, 5)

    def test_frozen_meld_from_meld(self):
        meld = Meld(
            meld_type=Meld.PON,
            tiles=[0, 1, 2],
            opened=True,
            called_tile=0,
            who=1,
            from_who=0,
        )
        frozen = FrozenMeld.from_meld(meld)
        assert frozen.tiles == (0, 1, 2)
        assert frozen.meld_type == Meld.PON
        assert frozen.opened is True
        assert frozen.called_tile == 0
        assert frozen.who == 1
        assert frozen.from_who == 0

    def test_frozen_meld_to_meld(self):
        frozen = FrozenMeld(
            tiles=(0, 1, 2),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=0,
            who=1,
            from_who=0,
        )
        meld = frozen.to_meld()
        assert meld.tiles == [0, 1, 2]
        assert meld.type == Meld.PON
        assert meld.opened is True
        assert meld.called_tile == 0
        assert meld.who == 1
        assert meld.from_who == 0

    def test_frozen_meld_type_constants(self):
        """Test that FrozenMeld type constants match expected string values."""
        assert FrozenMeld.CHI == "chi"
        assert FrozenMeld.PON == "pon"
        assert FrozenMeld.KAN == "kan"
        assert FrozenMeld.SHOUMINKAN == "shouminkan"
        assert FrozenMeld.CHANKAN == "chankan"

    def test_frozen_meld_type_constants_work_with_meld(self):
        """Test that FrozenMeld type constants work for comparison with Meld types."""
        meld = Meld(meld_type=Meld.PON, tiles=[0, 1, 2], opened=True)
        assert meld.type == FrozenMeld.PON

    def test_player_melds_frozen_meld_stored_directly(self):
        """Test that FrozenMeld objects are stored directly on MahjongPlayer."""
        frozen_meld = FrozenMeld(
            tiles=(0, 1, 2),
            meld_type=FrozenMeld.PON,
            opened=True,
        )
        player = MahjongPlayer(seat=0, name="Player1", melds=(frozen_meld,))
        assert len(player.melds) == 1
        assert player.melds[0] is frozen_meld

    def test_player_empty_melds(self):
        """Test that empty melds tuple is stored correctly."""
        player = MahjongPlayer(seat=0, name="Player1", melds=())
        assert player.melds == ()


class TestFrozenMeldsToMeldsFunction:
    def test_frozen_melds_to_melds_with_empty_tuple(self):
        """Test that frozen_melds_to_melds returns None for empty tuple."""
        result = frozen_melds_to_melds(())
        assert result is None

    def test_frozen_melds_to_melds_with_none(self):
        """Test that frozen_melds_to_melds returns None for None input."""
        result = frozen_melds_to_melds(None)
        assert result is None


class TestFrozenMeldScoringIntegration:
    def test_scoring_with_frozen_meld(self):
        """Test that calculate_hand_value works with FrozenMeld from frozen player."""
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
        result = calculate_hand_value(players[0], round_state, win_tile, is_tsumo=True)

        assert result.error is None
        assert result.han >= 1

    def test_can_declare_tsumo_with_frozen_meld(self):
        """Test that can_declare_tsumo works with FrozenMeld from frozen player."""
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

        result = can_declare_tsumo(players[0], round_state)
        assert result is True
