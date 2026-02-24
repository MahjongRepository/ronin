"""
Focused unit tests for the call resolution subsystem.

Tests cover resolution priority logic: single ron, double ron, triple ron
(abortive draw), meld priority (pon > chi), all-passed flow, chankan
decline completion, and DISCARD prompt resolution (four riichi abort after
ron pass).
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.call_resolution import (
    _action_to_meld_call_type,
    complete_added_kan_after_chankan_decline,
    pick_best_meld_response,
    resolve_call_prompt,
)
from game.logic.enums import (
    AbortiveDrawType,
    AIPlayerType,
    CallType,
    GameAction,
    MeldCallType,
    MeldViewType,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    DrawEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
)
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.state import (
    CallResponse,
    Discard,
    MahjongGameState,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
    MeldCaller,
    SeatConfig,
)
from game.tests.conftest import create_game_state, create_player, create_round_state


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


def _create_frozen_game_state() -> MahjongGameState:
    """Create a frozen game state for testing with dealer at seat 0."""
    game_state = init_game(_default_seat_configs(), wall=list(range(136)))
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


class TestActionToMeldCallTypeGuard:
    def test_unknown_action_raises(self):
        with pytest.raises(ValueError, match="no meld call type for action"):
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
        best = pick_best_meld_response(responses, prompt)
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
        best = pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 2

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
        best = pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 1  # distance 1 < distance 3

    def test_unknown_caller_filtered_out(self):
        """Responses from seats not in the original callers are ignored."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        # seat 2 was not a caller, so it should be filtered out
        responses = [
            CallResponse(seat=2, action=GameAction.CALL_PON),
        ]
        best = pick_best_meld_response(responses, prompt)
        assert best is None

    def test_ron_caller_fallback_to_pon(self):
        """Ron caller (int) that passes on ron and responds with pon is accepted."""
        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            # seat 2 is a ron caller (int), not a MeldCaller
            callers=(2,),
        )
        responses = [
            CallResponse(seat=2, action=GameAction.CALL_PON),
        ]
        best = pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 2

    def test_ron_caller_fallback_priority(self):
        """Ron caller falling back to pon competes fairly with MeldCaller."""
        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            # seat 1 is ron caller (int), seat 3 is meld caller (chi)
            callers=(1, MeldCaller(seat=3, call_type=MeldCallType.CHI, options=((4, 8),))),
        )
        responses = [
            CallResponse(seat=1, action=GameAction.CALL_PON),
            CallResponse(seat=3, action=GameAction.CALL_CHI, sequence_tiles=(4, 8)),
        ]
        # pon (priority 1) beats chi (priority 2)
        best = pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 1


class TestResolveSingleRon:
    def test_single_ron_resolves(self):
        """Single ron response resolves to RON round end."""
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
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
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
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
        assert len(result.events) == 0
        assert result.new_round_state is round_state


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
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        assert result.new_round_state.pending_call_prompt is None


class TestResolveChankanDecline:
    def test_chankan_all_passed_completes_kan(self):
        """All pass on chankan completes the added kan."""
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
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
        assert meld_events[0].meld_type == MeldViewType.ADDED_KAN


class TestCompleteAddedKanAfterChankanDecline:
    def test_completes_kan_with_draw_event(self):
        """Completing added kan after chankan decline emits meld and draw events."""
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
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
            round_state,
            game_state,
            caller_seat=0,
            tile_id=fourth_tile,
        )

        assert new_round_state is not None
        assert new_game_state is not None

        meld_events = [e for e in events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.ADDED_KAN

        draw_events = [e for e in events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 1
        assert draw_events[0].tile_id is not None
        assert draw_events[0].available_actions is not None

    def test_four_kans_abort_after_chankan_decline(self):
        """Completing 4th kan from different players triggers four kans abortive draw."""
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
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
            round_state,
            0,
            tiles=player_tiles,
            melds=(kan_meld_1, kan_meld_2, pon_meld),
        )
        round_state = update_player(round_state, 1, melds=(kan_meld_3,))
        game_state = game_state.model_copy(update={"round_state": round_state})

        new_round_state, _new_game_state, events = complete_added_kan_after_chankan_decline(
            round_state,
            game_state,
            caller_seat=0,
            tile_id=fourth_tile,
        )

        assert new_round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS


class TestResolvePonChiMeldResponse:
    """No DrawEvent after pon/chi — the MeldEvent is the only signal.

    Per mahjong rules, after calling pon/chi the only valid action is to
    discard a tile. The client infers turn ownership from MeldEvent.caller_seat.
    """

    def test_pon_emits_no_draw_event(self):
        """No DrawEvent after pon — only MeldEvent is emitted."""
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
        round_state = game_state.round_state

        # give seat 0 four of a kind (potential closed kan) plus other tiles
        four_of_kind = TilesConverter.string_to_136_array(sou="8888")
        other_tiles = TilesConverter.string_to_136_array(man="123", pin="456", sou="12")
        # also give 2 matching tiles for pon on the discarded tile
        pon_pair = TilesConverter.string_to_136_array(man="99")[:2]
        player_tiles = tuple(four_of_kind + other_tiles + pon_pair)
        round_state = update_player(round_state, 0, tiles=player_tiles)
        round_state = round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # seat 1 discards 9m, seat 0 calls pon
        discard_tile = TilesConverter.string_to_136_array(man="99")[1]
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=discard_tile,
            from_seat=1,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=0, call_type=MeldCallType.PON),),
            responses=(CallResponse(seat=0, action=GameAction.CALL_PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 0
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 0

    def test_chi_emits_no_draw_event(self):
        """No DrawEvent after chi — only MeldEvent is emitted."""
        game_state = init_game(_default_seat_configs(), wall=list(range(136)))
        round_state = game_state.round_state

        # seat 1 needs tiles forming a chi sequence (4m, 6m) to call chi on 5m
        chi_tiles = TilesConverter.string_to_136_array(man="46")
        other_tiles = TilesConverter.string_to_136_array(pin="123456789", sou="12")
        player_tiles = tuple(chi_tiles + other_tiles)
        round_state = update_player(round_state, 1, tiles=player_tiles)
        round_state = round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # seat 0 discards 5m, seat 1 (kamicha) calls chi
        discard_tile = TilesConverter.string_to_136_array(man="5")[0]
        sequence_tiles = (chi_tiles[0], chi_tiles[1])
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.CHI, options=(sequence_tiles,)),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_CHI, sequence_tiles=sequence_tiles),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 0
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 1


class TestMeldPromptFourRiichiAbort:
    """Four riichi abort triggered through MELD prompt resolution."""

    def test_four_riichi_abort_via_meld_prompt(self):
        """Riichi finalization triggers four-riichi abort through MELD prompt (no ron callers)."""
        # seat 0 is the discarder with pending riichi, seats 1-3 already in riichi
        discard_tile = TilesConverter.string_to_136_array(sou="5")[0]

        players = tuple(
            create_player(
                seat=i,
                tiles=tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113")) if i == 0 else (),
                is_riichi=(i in (1, 2, 3)),
                discards=(Discard(tile_id=discard_tile, is_riichi_discard=True),) if i == 0 else (),
            )
            for i in range(4)
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333366"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )

        # MELD prompt (not DISCARD) -- only meld callers, no ron
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(round_state, game_state)

        # riichi should be finalized even through MELD prompt
        riichi_events = [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert len(riichi_events) == 1
        assert riichi_events[0].seat == 0

        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI

    def test_meld_prompt_riichi_finalized_on_all_pass(self):
        """Riichi is finalized when all callers pass on a MELD prompt."""
        discard_tile = TilesConverter.string_to_136_array(sou="5")[0]

        players = tuple(
            create_player(
                seat=i,
                tiles=tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113")) if i == 0 else (),
                discards=(Discard(tile_id=discard_tile, is_riichi_discard=True),) if i == 0 else (),
            )
            for i in range(4)
        )

        wall = tuple(TilesConverter.string_to_136_array(man="5555"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333366"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(round_state, game_state)

        # riichi should be finalized
        riichi_events = [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert len(riichi_events) == 1
        assert riichi_events[0].seat == 0
        assert result.new_round_state.players[0].is_riichi is True


class TestResolveCallPromptPendingSeatsGuard:
    """Tests that resolve_call_prompt raises when pending_seats is not empty."""

    def test_raises_on_pending_seats(self):
        """Cannot resolve when some callers have not responded."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = create_round_state(
            pending_call_prompt=prompt,
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)

        with pytest.raises(ValueError, match="seats have not responded"):
            resolve_call_prompt(round_state, game_state)


class TestResolveCallPromptUnrecognizedMeldFallthrough:
    """Tests that unrecognized meld responses fall through to all-pass."""

    def test_unrecognized_meld_responses_treated_as_all_pass(self):
        """Meld responses from unrecognized callers fall through to all-pass logic."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
            responses=(CallResponse(seat=2, action=GameAction.CALL_PON),),
        )
        wall = tuple(TilesConverter.string_to_136_array(man="123456789"))
        dead_wall = tuple(TilesConverter.string_to_136_array(pin="11112222333344"))
        round_state = create_round_state(
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            pending_call_prompt=prompt,
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(round_state, game_state)

        assert result is not None
        assert result.new_round_state is not None
        assert result.new_round_state.pending_call_prompt is None
