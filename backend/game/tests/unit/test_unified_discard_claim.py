import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_pass, handle_pon, handle_ron
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    AbortiveDrawType,
    CallType,
    GameAction,
    MeldCallType,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import CallPromptEvent, DrawEvent, MeldEvent, RiichiDeclaredEvent, RoundEndEvent
from game.logic.exceptions import InvalidGameActionError
from game.logic.state import (
    CallResponse,
    Discard,
    PendingCallPrompt,
)
from game.logic.state_utils import update_game_with_round
from game.logic.turn import process_discard_phase
from game.logic.types import MeldCaller, PonActionData
from game.tests.conftest import create_game_state, create_player, create_round_state


def _make_wall_and_dead_wall():
    wall = tuple(TilesConverter.string_to_136_array(man="5555"))
    dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
    return wall, dead_wall


class TestRonPlusMeldCallersRonWins:
    def test_discard_claim__when_ron_and_meld_callers__should_resolve_ron(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(
            create_player(
                seat=i,
                tiles=(discard_tile,) if i == 0 else (ron_hand if i == 1 else (pon_tiles if i == 2 else ())),
            )
            for i in range(4)
        )

        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        # process_discard_phase creates a unified DISCARD prompt
        new_round, new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert len(call_prompts) == 1
        assert call_prompts[0].call_type == CallType.DISCARD

        # verify both callers are present
        ron_callers = [c for c in call_prompts[0].callers if isinstance(c, int)]
        meld_callers = [c for c in call_prompts[0].callers if isinstance(c, MeldCaller)]
        assert 1 in ron_callers
        assert any(c.seat == 2 for c in meld_callers)

        # simulate: B calls ron, C passes -> ron resolves
        prompt = new_round.pending_call_prompt
        assert prompt is not None
        resolved_prompt = prompt.model_copy(
            update={
                "pending_seats": frozenset(),
                "responses": (CallResponse(seat=1, action=GameAction.CALL_RON),),
            },
        )
        new_round = new_round.model_copy(update={"pending_call_prompt": resolved_prompt})
        new_game = update_game_with_round(new_game, new_round)

        result = resolve_call_prompt(new_round, new_game)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.RON


class TestRonPassMeldClaims:
    def test_discard_claim__when_ron_caller_passes_and_pon_claimed__should_execute_pon(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", sou="11")

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(
            create_player(
                seat=i,
                tiles=(
                    (discard_tile,)
                    if i == 0
                    else (ron_hand if i == 1 else ((*pon_tiles, *other_tiles) if i == 2 else ()))
                ),
            )
            for i in range(4)
        )

        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        new_round, new_game, _events = process_discard_phase(round_state, game_state, discard_tile)

        # simulate: B passes (ron caller), C calls pon
        prompt = new_round.pending_call_prompt
        assert prompt is not None
        resolved_prompt = prompt.model_copy(
            update={
                "pending_seats": frozenset(),
                "responses": (CallResponse(seat=2, action=GameAction.CALL_PON),),
            },
        )
        new_round = new_round.model_copy(update={"pending_call_prompt": resolved_prompt})
        new_game = update_game_with_round(new_game, new_round)

        result = resolve_call_prompt(new_round, new_game)

        # pon should execute - no DrawEvent, only MeldEvent
        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 0
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 2
        # round should NOT be finished
        assert result.new_round_state.phase == RoundPhase.PLAYING


class TestAllCallersPass:
    def test_discard_claim__when_all_callers_pass__should_advance_turn(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", sou="11")

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(
            create_player(
                seat=i,
                tiles=(
                    (discard_tile,)
                    if i == 0
                    else (ron_hand if i == 1 else ((*pon_tiles, *other_tiles) if i == 2 else ()))
                ),
            )
            for i in range(4)
        )

        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        new_round, new_game, _events = process_discard_phase(round_state, game_state, discard_tile)

        # all pass
        prompt = new_round.pending_call_prompt
        assert prompt is not None
        resolved_prompt = prompt.model_copy(
            update={"pending_seats": frozenset(), "responses": ()},
        )
        new_round = new_round.model_copy(update={"pending_call_prompt": resolved_prompt})
        new_game = update_game_with_round(new_game, new_round)

        result = resolve_call_prompt(new_round, new_game)

        # turn should advance, prompt cleared
        assert result.new_round_state.pending_call_prompt is None
        assert result.new_round_state.current_player_seat != 0


class TestMultipleRonPlusMeld:
    def test_discard_claim__when_two_ron_callers_and_meld_caller__should_resolve_double_ron(self):
        ron_hand_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        ron_hand_2 = tuple(TilesConverter.string_to_136_array(sou="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(
            create_player(
                seat=i,
                tiles=ron_hand_1 if i == 1 else (ron_hand_2 if i == 2 else ()),
            )
            for i in range(4)
        )

        # set up prompt directly: seats 1 and 2 are ron callers, seat 3 is meld
        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, 2, MeldCaller(seat=3, call_type=MeldCallType.PON)),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
            ),
        )

        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(round_state, game_state)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestAllRonPassMeldWins:
    def test_discard_claim__when_ron_callers_pass_and_pon_and_chi_claimed__should_execute_pon(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        chi_tiles = TilesConverter.string_to_136_array(pin="24")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", sou="11")

        wall, dead_wall = _make_wall_and_dead_wall()

        # seat 2 has pon tiles, seat 3 has chi tiles, seat 1 is ron caller (will pass)
        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                1,  # ron caller who passed
                MeldCaller(seat=2, call_type=MeldCallType.PON),
                MeldCaller(seat=3, call_type=MeldCallType.CHI, options=((chi_tiles[0], chi_tiles[1]),)),
            ),
            responses=(
                CallResponse(seat=2, action=GameAction.CALL_PON),
                CallResponse(seat=3, action=GameAction.CALL_CHI, sequence_tiles=(chi_tiles[0], chi_tiles[1])),
            ),
        )

        players = tuple(
            create_player(
                seat=i,
                tiles=((*pon_tiles, *other_tiles) if i == 2 else ((*chi_tiles, *other_tiles) if i == 3 else ())),
            )
            for i in range(4)
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(round_state, game_state)

        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 2  # pon wins over chi


class TestDualEligibleSeatRonDominant:
    def test_discard_claim__when_seat_eligible_for_ron_and_meld__should_offer_ron_only(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        wall, dead_wall = _make_wall_and_dead_wall()
        # seat 1 has ron hand AND can pon (has two pin 3s)
        players = tuple(
            create_player(
                seat=i,
                tiles=(discard_tile,) if i == 0 else (ron_hand if i == 1 else ()),
            )
            for i in range(4)
        )

        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        new_round, _new_game, _events = process_discard_phase(round_state, game_state, discard_tile)
        prompt = new_round.pending_call_prompt
        assert prompt is not None
        assert prompt.call_type == CallType.DISCARD

        # seat 1 should only be a ron caller (int), not meld caller
        seat1_callers = [c for c in prompt.callers if (isinstance(c, int) and c == 1)]
        seat1_melds = [c for c in prompt.callers if isinstance(c, MeldCaller) and c.seat == 1]
        assert len(seat1_callers) >= 1
        assert len(seat1_melds) == 0

    def test_discard_claim__when_ron_caller_responds_pon__should_reject(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),  # seat 1 is ron caller
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        with pytest.raises(InvalidGameActionError, match="only ron is valid"):
            handle_pon(round_state, game_state, 1, PonActionData(tile_id=discard_tile))


class TestDualEligibleSeatPassFuriten:
    def test_discard_claim__when_pass_on_ron_eligible_discard__should_apply_furiten(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),  # seat 1 is ron caller
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = handle_pass(round_state, game_state, 1)

        assert result.new_round_state.players[1].is_temporary_furiten is True

    def test_discard_claim__when_pass_on_meld_only_discard__should_not_apply_furiten(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({2}),
            callers=(MeldCaller(seat=2, call_type=MeldCallType.PON),),
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = handle_pass(round_state, game_state, 2)

        assert result.new_round_state.players[2].is_temporary_furiten is False


class TestRiichiFinalizationAfterRonPass:
    def test_discard_claim__when_riichi_discard_claimed_by_meld__should_finalize_riichi_first(self):
        discard_tile = TilesConverter.string_to_136_array(sou="5")[0]
        pon_tiles = TilesConverter.string_to_136_array(sou="55")
        other_tiles = TilesConverter.string_to_136_array(man="123456789", pin="11")

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(
            create_player(
                seat=i,
                tiles=(
                    tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113"))
                    if i == 0
                    else ((*pon_tiles, *other_tiles) if i == 2 else ())
                ),
                # seat 0 is the discarder, about to finalize riichi
                discards=(Discard(tile_id=discard_tile, is_riichi_discard=True),) if i == 0 else (),
            )
            for i in range(4)
        )

        # create a DISCARD prompt with seat 1 as ron caller (already passed) and seat 2 as meld
        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, MeldCaller(seat=2, call_type=MeldCallType.PON)),
            responses=(CallResponse(seat=2, action=GameAction.CALL_PON),),
        )

        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(round_state, game_state)

        # riichi should be finalized first
        riichi_events = [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert len(riichi_events) == 1
        assert riichi_events[0].seat == 0

        # meld (pon) should execute - no DrawEvent, only MeldEvent
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 2


class TestFourRiichiAbortAfterRonPass:
    def test_discard_claim__when_fourth_riichi_discard_unclaimed__should_abort_four_riichi(self):
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

        wall, dead_wall = _make_wall_and_dead_wall()
        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1,),  # seat 1 was a ron caller who passed
        )

        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(round_state, game_state)

        riichi_events = [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert len(riichi_events) == 1
        assert riichi_events[0].seat == 0

        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.ABORTIVE_DRAW
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI


class TestHandleRonOnDiscardPrompt:
    def test_discard_claim__when_ron_called_with_other_callers_pending__should_record_response_and_keep_prompt(self):
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(1, MeldCaller(seat=2, call_type=MeldCallType.PON)),
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(
            create_player(
                seat=i,
                tiles=ron_hand if i == 1 else (),
            )
            for i in range(4)
        )
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        result = handle_ron(round_state, game_state, 1)

        # should record response and wait for seat 2
        assert result.new_round_state.pending_call_prompt is not None
        responses = result.new_round_state.pending_call_prompt.responses
        assert len(responses) == 1
        assert responses[0].seat == 1
        assert responses[0].action == GameAction.CALL_RON


class TestHandlePassThenResolve:
    def test_discard_claim__when_both_callers_pass__should_clear_prompt_and_advance_turn(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(1, MeldCaller(seat=2, call_type=MeldCallType.PON)),
        )

        wall, dead_wall = _make_wall_and_dead_wall()
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
            pending_call_prompt=prompt,
        )
        game_state = create_game_state(round_state)

        # seat 1 passes (ron caller -> furiten applied)
        result1 = handle_pass(round_state, game_state, 1)
        assert result1.new_round_state.players[1].is_temporary_furiten is True

        # seat 2 passes (meld caller -> no furiten)
        result2 = handle_pass(result1.new_round_state, result1.new_game_state, 2)

        # should be resolved (turn advanced)
        assert result2.new_round_state.pending_call_prompt is None
        assert result2.new_round_state.current_player_seat != 0


class TestLastDiscardRestriction:
    def test_discard_claim__when_last_discard__should_block_pon(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        # tiles that do NOT form a winning hand with pin333
        other_tiles = TilesConverter.string_to_136_array(man="1234", sou="1234567")

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="88889999", pin="112266"))
        players = tuple(
            create_player(
                seat=i,
                tiles=((discard_tile,) if i == 0 else ((*pon_tiles, *other_tiles) if i == 2 else ())),
            )
            for i in range(4)
        )

        # empty live wall: last tile was already drawn
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        # no call prompt should be created (no ron callers either in this scenario)
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert len(call_prompts) == 0

    def test_discard_claim__when_last_discard__should_block_chi(self):
        discard_tile = TilesConverter.string_to_136_array(pin="5")[0]
        chi_tiles = TilesConverter.string_to_136_array(pin="46")
        # tiles that do NOT form a winning hand with pin456
        other_tiles = TilesConverter.string_to_136_array(man="1234", sou="1234567")

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="88889999", pin="112233"))
        players = tuple(
            create_player(
                seat=i,
                tiles=((discard_tile,) if i == 0 else ((*chi_tiles, *other_tiles) if i == 1 else ())),
            )
            for i in range(4)
        )

        # empty live wall
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert len(call_prompts) == 0

    def test_discard_claim__when_last_discard__should_allow_ron(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333366"))
        players = tuple(
            create_player(
                seat=i,
                tiles=((discard_tile,) if i == 0 else (ron_hand if i == 1 else ())),
            )
            for i in range(4)
        )

        # empty live wall
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        # a call prompt should exist with only ron callers
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert len(call_prompts) == 1
        prompt = call_prompts[0]
        # all callers should be ron callers (int), not meld callers
        for caller in prompt.callers:
            assert isinstance(caller, int), f"expected ron caller (int), got MeldCaller: {caller}"

    def test_discard_claim__when_last_discard_pon_and_ron_possible__should_offer_ron_only(self):
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]
        ron_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        pon_tiles = TilesConverter.string_to_136_array(pin="33")
        # tiles that do NOT form a winning hand with pin333
        other_tiles = TilesConverter.string_to_136_array(man="1234", sou="1234567")

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="88889999", pin="112266"))
        players = tuple(
            create_player(
                seat=i,
                tiles=(
                    (discard_tile,)
                    if i == 0
                    else (ron_hand if i == 1 else ((*pon_tiles, *other_tiles) if i == 2 else ()))
                ),
            )
            for i in range(4)
        )

        # empty live wall
        round_state = create_round_state(
            players=players,
            wall=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=0,
        )
        game_state = create_game_state(round_state)

        _new_round, _new_game, events = process_discard_phase(round_state, game_state, discard_tile)

        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        assert len(call_prompts) == 1
        prompt = call_prompts[0]
        # ron caller (seat 1) should be present, meld caller (seat 2) should not
        ron_callers = [c for c in prompt.callers if isinstance(c, int)]
        meld_callers = [c for c in prompt.callers if isinstance(c, MeldCaller)]
        assert 1 in ron_callers
        assert len(meld_callers) == 0
