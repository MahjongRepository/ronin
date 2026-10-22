import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import GameAction, PromptKind, WindName
from game.logic.meld_wrapper import FrozenMeld, frozen_melds_to_melds
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings
from game.logic.state import (
    Caller,
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
    add_prompt_response,
    add_tile_to_player,
    advance_turn,
    clear_all_players_ippatsu,
    clear_pending_prompt,
    update_player,
)
from game.logic.wall import Wall


class TestMahjongPlayerLogic:
    def test_has_open_melds__when_open_meld__should_be_true(self):
        open_meld = FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True)
        player = MahjongPlayer(seat=0, name="P1", melds=(open_meld,), score=25000)
        assert player.has_open_melds() is True

    def test_has_open_melds__when_only_closed_meld__should_be_false(self):
        closed_meld = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=False)
        player = MahjongPlayer(seat=0, name="P2", melds=(closed_meld,), score=25000)
        assert player.has_open_melds() is False

    def test_has_open_melds__when_no_melds__should_be_false(self):
        player = MahjongPlayer(seat=0, name="P3", score=25000)
        assert player.has_open_melds() is False


class TestFrozenMeldsToMeldsFunction:
    def test_frozen_melds_to_melds__when_empty_tuple__should_return_none(self):
        assert frozen_melds_to_melds(()) is None

    def test_frozen_melds_to_melds__when_none__should_return_none(self):
        assert frozen_melds_to_melds(None) is None


class TestStateUtilsUpdatePlayer:
    def _create_round_state_with_players(self) -> MahjongRoundState:
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        return MahjongRoundState(players=players)

    def test_update_player__when_score_changed__should_leave_original_state_untouched(self):
        state = self._create_round_state_with_players()

        new_state = update_player(state, 0, score=30000)
        assert state.players[0].score == 25000
        assert new_state.players[0].score == 30000
        assert new_state.players[1].score == 25000

    def test_update_player__when_multiple_fields__should_apply_all(self):
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

    def test_add_tile_to_player__should_append_tile_without_mutating_original(self):
        state = self._create_round_state_with_tiles()
        new_tile = TilesConverter.string_to_136_array(pin="1")[0]

        new_state = add_tile_to_player(state, seat=0, tile_id=new_tile)
        assert len(state.players[0].tiles) == 9
        assert len(new_state.players[0].tiles) == 10
        assert new_state.players[0].tiles[-1] == new_tile


class TestStateUtilsTurnAdvance:
    def _players(self) -> tuple[MahjongPlayer, ...]:
        return tuple(MahjongPlayer(seat=i, name=f"P{i}", score=25000) for i in range(4))

    def test_advance_turn__should_move_to_next_seat(self):
        state = MahjongRoundState(players=self._players(), current_player_seat=0)

        new_state = advance_turn(state)
        assert state.current_player_seat == 0
        assert new_state.current_player_seat == 1

    def test_advance_turn__when_current_seat_is_last__should_wrap_to_seat_zero(self):
        state = MahjongRoundState(players=self._players(), current_player_seat=3)

        new_state = advance_turn(state)
        assert new_state.current_player_seat == 0


class TestPendingCallPromptCaller:
    def test_pending_call_prompt_caller__when_seat_is_not_a_caller__should_raise_assertion_error(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, can_ron=True),),
        )

        assert prompt.caller(1) == Caller(seat=1, can_ron=True)
        with pytest.raises(AssertionError, match="seat 2 is not a caller"):
            prompt.caller(2)


class TestStateUtilsPendingPrompt:
    def test_clear_pending_prompt__should_remove_prompt_from_new_state(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, can_ron=True),),
        )
        state = MahjongRoundState(pending_call_prompt=prompt)

        new_state = clear_pending_prompt(state)
        assert state.pending_call_prompt is not None
        assert new_state.pending_call_prompt is None

    def test_add_prompt_response__should_record_response_and_remove_pending_seat(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True)),
        )
        response = CallResponse(seat=1, action=GameAction.PASS)

        new_prompt = add_prompt_response(prompt, response)
        assert len(prompt.responses) == 0
        assert prompt.pending_seats == frozenset({1, 2})
        assert len(new_prompt.responses) == 1
        assert new_prompt.pending_seats == frozenset({2})

    def test_add_prompt_response__when_seat_not_pending__should_raise_key_error(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, can_ron=True),),
        )
        response = CallResponse(seat=3, action=GameAction.PASS)
        with pytest.raises(KeyError):
            add_prompt_response(prompt, response)


class TestStateUtilsPlayerFlags:
    def test_clear_all_players_ippatsu__should_clear_flag_for_every_player(self):
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
    def test_scoring__when_hand_has_frozen_meld__should_score_without_error(self):
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        discard1 = Discard(tile_id=0, is_tsumogiri=False)
        frozen_meld = FrozenMeld(
            tiles=tuple(haku_tiles),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )
        players = (
            MahjongPlayer(
                seat=0,
                name="Player0",
                tiles=tuple(closed_tiles),
                melds=(frozen_meld,),
                discards=(discard1,),
                score=25000,
            ),
            MahjongPlayer(seat=1, name="Player1", discards=(discard1,), score=25000),
            MahjongPlayer(seat=2, name="Player2", discards=(discard1,), score=25000),
            MahjongPlayer(seat=3, name="Player3", discards=(discard1,), score=25000),
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
        assert result.han == 4
        assert result.fu == 30


class TestUpdatePlayerValidation:
    def _create_round_state(self) -> MahjongRoundState:
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        return MahjongRoundState(players=players)

    def test_update_player__when_seat_negative__should_raise_value_error(self):
        state = self._create_round_state()
        with pytest.raises(ValueError, match="Invalid seat -1"):
            update_player(state, -1, score=30000)

    def test_update_player__when_seat_out_of_bounds__should_raise_value_error(self):
        state = self._create_round_state()
        with pytest.raises(ValueError, match="Invalid seat 4"):
            update_player(state, 4, score=30000)

    def test_update_player__when_field_name_invalid__should_raise_value_error(self):
        state = self._create_round_state()
        with pytest.raises(ValueError, match="Invalid player fields"):
            update_player(state, 0, nonexistent_field=True)


class TestGetPlayerViewValidation:
    def test_get_player_view__when_seat_not_found__should_raise_value_error(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(players=players)
        game_state = MahjongGameState(round_state=round_state)

        with pytest.raises(ValueError, match="No player found at seat 5"):
            get_player_view(game_state, 5)

    def test_get_player_view__when_seat_valid__should_return_view(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", tiles=(i,), score=25000) for i in range(4))
        round_state = MahjongRoundState(players=players)
        game_state = MahjongGameState(round_state=round_state)

        view = get_player_view(game_state, 2)
        assert view.seat == 2
        assert view.my_tiles == [2]


class TestWindNameConstant:
    def test_wind_name__when_out_of_range__should_return_unknown(self):
        assert wind_name(-1) == WindName.UNKNOWN
        assert wind_name(4) == WindName.UNKNOWN
        assert wind_name(100) == WindName.UNKNOWN
