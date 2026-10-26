import pytest
from mahjong.tile import TilesConverter

from game.logic.call_resolution import (
    complete_added_kan_after_chankan_decline,
    pick_best_meld_response,
    resolve_call_prompt,
)
from game.logic.enums import (
    AIPlayerType,
    GameAction,
    MeldCallType,
    MeldViewType,
    PromptKind,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    DrawEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    SeatTarget,
    TurnEvent,
)
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.state import (
    Caller,
    CallResponse,
    Discard,
    MeldOption,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
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


class TestPickBestMeldResponse:
    def test_pick_best_meld_response__when_pon_and_chi__should_prefer_pon(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.PON),)),
                Caller(seat=3, melds=(MeldOption(call_type=MeldCallType.CHI),)),
            ),
        )

        responses = [
            CallResponse(seat=3, action=GameAction.CALL_CHI),
            CallResponse(seat=1, action=GameAction.CALL_PON),
        ]
        best = pick_best_meld_response(responses, prompt)
        assert best.seat == 1

    def test_pick_best_meld_response__when_kan_and_pon__should_prefer_kan(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.PON),)),
                Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.OPEN_KAN),)),
            ),
        )

        responses = [
            CallResponse(seat=1, action=GameAction.CALL_PON),
            CallResponse(seat=2, action=GameAction.CALL_KAN),
        ]
        best = pick_best_meld_response(responses, prompt)
        assert best.seat == 2

    def test_pick_best_meld_response__when_same_call_type__should_prefer_closest_seat(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.PON),)),
                Caller(seat=3, melds=(MeldOption(call_type=MeldCallType.PON),)),
            ),
        )

        responses = [
            CallResponse(seat=3, action=GameAction.CALL_PON),
            CallResponse(seat=1, action=GameAction.CALL_PON),
        ]
        best = pick_best_meld_response(responses, prompt)
        assert best.seat == 1


class TestResolveWithoutPrompt:
    def test_resolve_call_prompt__when_no_prompt_pending__should_raise_assertion_error(self):
        round_state = create_round_state(phase=RoundPhase.PLAYING)

        with pytest.raises(AssertionError, match="no pending call prompt"):
            resolve_call_prompt(create_game_state(round_state))


class TestResolveSingleRon:
    def test_resolve_call_prompt__when_single_ron__should_end_round_with_ron(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 1 a waiting hand
        waiting_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        round_state = update_player(round_state, 1, tiles=waiting_tiles)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_RON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(game_state)
        assert result.state.round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.RON


class TestResolveDoubleRon:
    def test_resolve_call_prompt__when_two_rons__should_end_round_with_double_ron(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 1 and 2 waiting hands
        waiting_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        waiting_tiles_2 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        round_state = update_player(round_state, 1, tiles=waiting_tiles_1)
        round_state = update_player(round_state, 2, tiles=waiting_tiles_2)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True)),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(game_state)
        assert result.state.round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestResolveChankanDecline:
    def test_resolve_call_prompt__when_all_pass_chankan__should_complete_added_kan(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
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
            kind=PromptKind.CHANKAN,
            tile_id=fourth_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True),),
            responses=(),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        result = resolve_call_prompt(game_state)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.ADDED_KAN


class TestCompleteAddedKanAfterChankanDecline:
    def test_complete_added_kan__should_emit_meld_and_rinshan_draw(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
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

        new_game_state, events = complete_added_kan_after_chankan_decline(
            game_state,
            caller_seat=0,
            tile_id=fourth_tile,
        )
        new_round_state = new_game_state.round_state
        assert new_round_state is not None
        assert new_game_state is not None
        meld_events = [e for e in events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.ADDED_KAN
        draw_events = [e for e in events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 1
        assert draw_events[0].tile_id is not None
        assert draw_events[0].available_actions is not None


class TestResolvePonChiMeldResponse:
    def test_resolve_meld_response__when_pon__should_emit_meld_then_turn_event_forbidding_the_called_type(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
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
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=1,
            pending_seats=frozenset(),
            callers=(Caller(seat=0, melds=(MeldOption(call_type=MeldCallType.PON),)),),
            responses=(CallResponse(seat=0, action=GameAction.CALL_PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(game_state)
        assert [type(e) for e in result.events] == [MeldEvent, TurnEvent]
        meld_event, turn_event = result.events
        assert meld_event.caller_seat == 0
        assert turn_event.target == SeatTarget(seat=0)
        assert turn_event.kuikae_tiles == [discard_tile // 4]

    def test_resolve_meld_response__when_chi__should_emit_meld_then_turn_event(self):
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
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
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.CHI, options=(sequence_tiles,)),)),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_CHI, sequence_tiles=sequence_tiles),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(game_state)
        assert [type(e) for e in result.events] == [MeldEvent, TurnEvent]
        assert result.events[0].caller_seat == 1
        assert result.events[1].target == SeatTarget(seat=1)


class TestRiichiDiscardAllPass:
    def test_resolve_call_prompt__when_all_pass_on_riichi_discard__should_finalize_riichi(self):
        discard_tile = TilesConverter.string_to_136_array(sou="5")[0]

        players = (
            create_player(
                seat=0,
                tiles=tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113")),
                discards=(Discard(tile_id=discard_tile, is_riichi_discard=True),),
            ),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
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
            kind=PromptKind.DISCARD,
            tile_id=discard_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = create_game_state(round_state)

        result = resolve_call_prompt(game_state)
        riichi_events = [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert len(riichi_events) == 1
        assert riichi_events[0].seat == 0
        assert result.state.round_state.players[0].is_riichi is True
