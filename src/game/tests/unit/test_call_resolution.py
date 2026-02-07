"""
Focused unit tests for the call resolution subsystem.

Tests cover resolution priority logic: single ron, double ron, triple ron
(abortive draw), meld priority (pon > chi), all-passed flow, and chankan
decline completion.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.action_result import ActionResult
from game.logic.call_resolution import (
    _action_to_meld_call_type,
    _pick_best_meld_response,
    complete_added_kan_after_chankan_decline,
    resolve_call_prompt,
)
from game.logic.enums import (
    AbortiveDrawType,
    BotType,
    CallType,
    GameAction,
    KanType,
    MeldCallType,
    MeldViewType,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    DrawEvent,
    MeldEvent,
    RoundEndEvent,
    TurnEvent,
)
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.state import (
    CallResponse,
    MahjongGameState,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
    MeldCaller,
    SeatConfig,
)


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", bot_type=BotType.TSUMOGIRI),
    ]


def _create_frozen_game_state(seed: float = 12345.0) -> MahjongGameState:
    """Create a frozen game state for testing."""
    game_state = init_game(_default_seat_configs(), seed=seed)
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


class TestActionToMeldCallType:
    def test_pon_mapping(self):
        assert _action_to_meld_call_type(GameAction.CALL_PON) == MeldCallType.PON

    def test_chi_mapping(self):
        assert _action_to_meld_call_type(GameAction.CALL_CHI) == MeldCallType.CHI

    def test_kan_mapping(self):
        assert _action_to_meld_call_type(GameAction.CALL_KAN) == MeldCallType.OPEN_KAN

    def test_unknown_action_raises(self):
        with pytest.raises(KeyError):
            _action_to_meld_call_type(GameAction.DISCARD)


class TestPickBestMeldResponse:
    def test_pon_over_chi(self):
        """Pon has higher priority than chi."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=3, call_type=MeldCallType.CHI),
            ),
        )
        responses = [
            CallResponse(seat=3, action=GameAction.CALL_CHI),
            CallResponse(seat=1, action=GameAction.CALL_PON),
        ]
        best = _pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 1

    def test_kan_over_pon(self):
        """Kan has higher priority than pon."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=2, call_type=MeldCallType.OPEN_KAN),
            ),
        )
        responses = [
            CallResponse(seat=1, action=GameAction.CALL_PON),
            CallResponse(seat=2, action=GameAction.CALL_KAN),
        ]
        best = _pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 2

    def test_empty_responses(self):
        """No responses returns None."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        best = _pick_best_meld_response([], prompt)
        assert best is None

    def test_distance_tiebreak(self):
        """Same priority: closer counter-clockwise distance wins."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=3, call_type=MeldCallType.PON),
            ),
        )
        responses = [
            CallResponse(seat=3, action=GameAction.CALL_PON),
            CallResponse(seat=1, action=GameAction.CALL_PON),
        ]
        best = _pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 1  # distance 1 < distance 3


class TestResolveSingleRon:
    def test_single_ron_resolves(self):
        """Single ron response resolves to RON round end."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a waiting hand
        waiting_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        round_state = update_player(round_state, 1, tiles=waiting_tiles)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1,),
            responses=(CallResponse(seat=1, action=GameAction.CALL_RON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        assert result.new_round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.RON


class TestResolveDoubleRon:
    def test_double_ron_resolves(self):
        """Two ron responses resolve to DOUBLE_RON round end."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 and 2 waiting hands
        waiting_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        waiting_tiles_2 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        round_state = update_player(round_state, 1, tiles=waiting_tiles_1)
        round_state = update_player(round_state, 2, tiles=waiting_tiles_2)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, 2),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        assert result.new_round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestResolveTripleRon:
    def test_triple_ron_abortive_draw(self):
        """Three ron responses trigger triple ron abortive draw."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, 2, 3),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
                CallResponse(seat=3, action=GameAction.CALL_RON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        assert result.new_round_state.phase == RoundPhase.FINISHED
        end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(end_events) == 1
        assert end_events[0].result.reason == AbortiveDrawType.TRIPLE_RON


class TestResolveNoPrompt:
    def test_no_prompt_returns_empty(self):
        """No pending prompt returns empty result with unchanged state."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = resolve_call_prompt(round_state, game_state)

        assert isinstance(result, ActionResult)
        assert len(result.events) == 0
        assert result.new_round_state is round_state
        assert result.new_game_state is game_state


class TestResolveAllPassed:
    def test_all_passed_advances_turn(self):
        """All passes on a meld prompt advance the turn."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
            responses=(),
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING}
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        assert result.new_round_state.pending_call_prompt is None


class TestResolveChankanDecline:
    def test_chankan_all_passed_completes_kan(self):
        """All pass on chankan completes the added kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        new_round_state, _tile = draw_tile(game_state.round_state)

        tile_ids = TilesConverter.string_to_136_array(man="1111")
        pon_tiles = tile_ids[:3]
        fourth_tile = tile_ids[3]
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player_tiles = (fourth_tile, *new_round_state.players[0].tiles[:-1])
        new_round_state = update_player(new_round_state, 0, tiles=player_tiles, melds=(pon_meld,))
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=fourth_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1,),
            responses=(),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        result = resolve_call_prompt(new_round_state, game_state)

        assert result.new_round_state is not None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN
        assert meld_events[0].kan_type == KanType.ADDED


class TestCompleteAddedKanAfterChankanDecline:
    def test_completes_kan_with_draw_and_turn_events(self):
        """Completing added kan after chankan decline emits meld, draw, and turn events."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        tile_ids = TilesConverter.string_to_136_array(man="1111")
        pon_tiles = tile_ids[:3]
        fourth_tile = tile_ids[3]
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        new_tiles = (fourth_tile, *round_state.players[0].tiles[:-1])
        round_state = update_player(round_state, 0, tiles=new_tiles, melds=(pon_meld,))
        game_state = game_state.model_copy(update={"round_state": round_state})

        new_round_state, new_game_state, events = complete_added_kan_after_chankan_decline(
            round_state, game_state, caller_seat=0, tile_id=fourth_tile
        )

        assert new_round_state is not None
        assert new_game_state is not None

        meld_events = [e for e in events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN
        assert meld_events[0].kan_type == KanType.ADDED

        draw_events = [e for e in events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 1

        turn_events = [e for e in events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1

    def test_four_kans_abort_after_chankan_decline(self):
        """Completing 4th kan from different players triggers four kans abortive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        # create 2 existing kans for player 0
        kan_tiles_1 = TilesConverter.string_to_136_array(man="1111")
        kan_tiles_2 = TilesConverter.string_to_136_array(man="2222")
        kan_meld_1 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_1),
            opened=False,
            called_tile=kan_tiles_1[0],
            who=0,
            from_who=0,
        )
        kan_meld_2 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_2),
            opened=False,
            called_tile=kan_tiles_2[0],
            who=0,
            from_who=0,
        )

        # 1 kan for player 1
        kan_tiles_3 = TilesConverter.string_to_136_array(man="3333")
        kan_meld_3 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_3),
            opened=True,
            called_tile=kan_tiles_3[0],
            who=1,
            from_who=2,
        )

        # pon for player 0 that will become 4th kan
        pon_tiles = TilesConverter.string_to_136_array(man="4444")[:3]
        fourth_tile = TilesConverter.string_to_136_array(man="4444")[3]
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player_tiles = (fourth_tile, *round_state.players[0].tiles[:12])
        round_state = update_player(
            round_state, 0, tiles=player_tiles, melds=(kan_meld_1, kan_meld_2, pon_meld)
        )
        round_state = update_player(round_state, 1, melds=(kan_meld_3,))
        game_state = game_state.model_copy(update={"round_state": round_state})

        new_round_state, _new_game_state, events = complete_added_kan_after_chankan_decline(
            round_state, game_state, caller_seat=0, tile_id=fourth_tile
        )

        assert new_round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS
