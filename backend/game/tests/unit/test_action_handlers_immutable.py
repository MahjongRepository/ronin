from mahjong.tile import TilesConverter

from game.logic.action_handlers import (
    handle_chi,
    handle_discard,
    handle_kan,
    handle_kyuushu,
    handle_pass,
    handle_pon,
    handle_riichi,
    handle_ron,
    handle_tsumo,
)
from game.logic.action_result import ActionResult, Refusal
from game.logic.call_resolution import (
    complete_added_kan_after_chankan_decline,
    resolve_call_prompt,
)
from game.logic.enums import (
    AbortiveDrawType,
    AIPlayerType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    MeldViewType,
    PromptKind,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    DiscardEvent,
    DrawEvent,
    MeldEvent,
    RoundEndEvent,
)
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.state import (
    Caller,
    CallResponse,
    Discard,
    MahjongGameState,
    MeldOption,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
    AbortiveDrawResult,
    ChiActionData,
    DiscardActionData,
    KanActionData,
    PonActionData,
    RiichiActionData,
    SeatConfig,
)


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


def _create_frozen_game_state() -> MahjongGameState:
    game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


class TestHandleDiscardImmutable:
    def test_handle_discard__should_remove_tile_in_new_state_and_emit_discard_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        result = handle_discard(
            game_state,
            seat=0,
            data=DiscardActionData(tile_id=tile_to_discard),
        )
        assert isinstance(result, ActionResult)
        assert result.needs_post_discard is True
        # verify new state is returned
        # verify original state is unchanged
        assert round_state.players[0].tiles == game_state.round_state.players[0].tiles
        # verify the tile was removed from new state
        assert tile_to_discard not in result.state.round_state.players[0].tiles
        # verify discard event is produced
        discard_events = [e for e in result.events if isinstance(e, DiscardEvent)]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard


class TestHandleRiichiImmutable:
    def _create_riichi_hand(self) -> MahjongGameState:
        # use a different seed to get a riichi-able hand
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player a tenpai hand
        tenpai_tiles = TilesConverter.string_to_136_array(man="123456789", sou="123", pin="11")
        new_round_state = update_player(new_round_state, 0, tiles=tuple(tenpai_tiles[:14]), score=26000)
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_handle_riichi__when_valid__should_emit_riichi_discard(self):
        game_state = self._create_riichi_hand()
        round_state = game_state.round_state

        # discard the last tile (14th tile) for riichi
        tile_to_discard = round_state.players[0].tiles[-1]
        result = handle_riichi(
            game_state,
            seat=0,
            data=RiichiActionData(tile_id=tile_to_discard),
        )
        assert isinstance(result, ActionResult)
        assert result.needs_post_discard is True
        # should have discard event
        discard_events = [e for e in result.events if isinstance(e, DiscardEvent)]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard
        assert discard_events[0].is_riichi is True

    def test_handle_riichi__when_not_players_turn__should_refuse_with_not_your_turn(self):
        game_state = _create_frozen_game_state()

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        result = handle_riichi(game_state, seat=1, data=RiichiActionData(tile_id=tile_id))
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.NOT_YOUR_TURN


class TestHandleTsumoImmutable:
    def _create_winning_game_state(self) -> MahjongGameState:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 0 a complete winning hand (14 tiles)
        # 123m 456m 789m 111p 22p
        winning_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="11122"))
        round_state = update_player(round_state, 0, tiles=winning_tiles)
        return game_state.model_copy(update={"round_state": round_state})

    def test_handle_tsumo__when_valid__should_end_round_with_tsumo(self):
        game_state = self._create_winning_game_state()

        result = handle_tsumo(game_state, seat=0)
        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.TSUMO
        assert result.state.round_state.phase == RoundPhase.FINISHED
        assert result.state.round_state.result == round_end_events[0].result


class TestHandleRonImmutable:
    def _create_ron_prompt_state(
        self,
        pending_seats: frozenset[int] = frozenset({1, 2}),
    ) -> MahjongGameState:
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=pending_seats,
            callers=tuple(Caller(seat=seat, can_ron=True) for seat in sorted(pending_seats)),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        return game_state.model_copy(update={"round_state": round_state})

    def _create_ron_opportunity(self) -> tuple[MahjongGameState, int, int]:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 1 a waiting hand: 123m 456m 789m 111p 2p
        waiting_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        round_state = update_player(round_state, 1, tiles=waiting_tiles)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]  # 2p (2nd copy)
        game_state = game_state.model_copy(update={"round_state": round_state})

        return game_state, win_tile, 0

    def test_handle_ron__when_valid__should_end_round_with_ron(self):
        game_state, win_tile, discarder_seat = self._create_ron_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for ron
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=win_tile,
            from_seat=discarder_seat,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, can_ron=True),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_ron(game_state, seat=1)
        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.RON

    def test_handle_ron__when_other_callers_pending__should_record_response_and_wait(self):
        game_state = self._create_ron_prompt_state(frozenset({1, 2}))

        result = handle_ron(game_state, seat=1)
        # should update prompt with response but NOT resolve yet (seat 2 still pending)
        # check that the response was added
        prompt = result.state.round_state.pending_call_prompt
        assert prompt is not None
        assert len(prompt.responses) == 1
        assert prompt.responses[0].seat == 1
        assert prompt.responses[0].action == GameAction.CALL_RON
        # seat 1 should be removed from pending
        assert 1 not in prompt.pending_seats
        assert 2 in prompt.pending_seats


class TestHandlePonImmutable:
    def _create_pon_opportunity(self) -> tuple[MahjongGameState, int]:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 1 two 1m tiles + filler
        player1_tiles = tuple(
            TilesConverter.string_to_136_array(man="11368", pin="2479", sou="358", honors="1"),
        )
        round_state = update_player(round_state, 1, tiles=player1_tiles)

        tile_to_pon = TilesConverter.string_to_136_array(man="111")[2]  # 1m (3rd copy)
        game_state = game_state.model_copy(update={"round_state": round_state})

        return game_state, tile_to_pon

    def test_handle_pon__when_valid__should_emit_pon_meld_without_draw(self):
        game_state, tile_to_pon = self._create_pon_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for meld
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=tile_to_pon,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_pon(game_state, seat=1, data=PonActionData(tile_id=tile_to_pon))
        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON
        assert meld_events[0].caller_seat == 1
        # no DrawEvent after pon — MeldEvent is the only signal
        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 0


class TestHandleChiImmutable:
    def _create_chi_opportunity(self) -> tuple[MahjongGameState, int, tuple[int, int]]:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # player 1 has 2m and 3m tiles + filler
        player1_tiles = tuple(TilesConverter.string_to_136_array(man="236789", pin="2345789"))
        round_state = update_player(round_state, 1, tiles=player1_tiles)

        # player 0 discards 1m
        tile_to_chi = TilesConverter.string_to_136_array(man="1")[0]
        seq_tiles = TilesConverter.string_to_136_array(man="23")

        game_state = game_state.model_copy(update={"round_state": round_state})
        return game_state, tile_to_chi, (seq_tiles[0], seq_tiles[1])

    def test_handle_chi__when_valid__should_emit_chi_meld_without_draw(self):
        game_state, tile_to_chi, sequence_tiles = self._create_chi_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for meld
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=tile_to_chi,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.CHI, options=(sequence_tiles,)),)),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_chi(
            game_state,
            seat=1,
            data=ChiActionData(tile_id=tile_to_chi, sequence_tiles=sequence_tiles),
        )
        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CHI
        # no DrawEvent after chi — MeldEvent is the only signal
        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 0

    def test_handle_chi__when_no_prompt__should_refuse_with_invalid_chi(self):
        game_state = _create_frozen_game_state()

        result = handle_chi(
            game_state,
            seat=1,
            data=ChiActionData(tile_id=0, sequence_tiles=(1, 2)),
        )
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.INVALID_CHI


class TestHandleKanImmutable:
    def _create_closed_kan_opportunity(self) -> tuple[MahjongGameState, int]:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 0 four 1m tiles + filler
        kan_tiles = tuple(TilesConverter.string_to_136_array(man="1111368", pin="2479", sou="35"))
        round_state = update_player(round_state, 0, tiles=kan_tiles)
        round_state, _tile = draw_tile(round_state)

        game_state = game_state.model_copy(update={"round_state": round_state})
        return game_state, TilesConverter.string_to_136_array(man="1")[0]

    def test_handle_kan__when_closed_kan__should_emit_closed_kan_meld(self):
        game_state, tile_id = self._create_closed_kan_opportunity()

        result = handle_kan(
            game_state,
            seat=0,
            data=KanActionData(tile_id=tile_id, kan_type=KanType.CLOSED),
        )
        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CLOSED_KAN

    def test_handle_kan__when_closed_kan_out_of_turn__should_refuse_with_not_your_turn(self):
        game_state = _create_frozen_game_state()

        result = handle_kan(
            game_state,
            seat=1,
            data=KanActionData(tile_id=0, kan_type=KanType.CLOSED),
        )
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.NOT_YOUR_TURN

    def _create_open_kan_opportunity(self) -> tuple[MahjongGameState, int]:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]
        # give player 1 three 5m tiles + filler for open kan
        player1_tiles = tuple(TilesConverter.string_to_136_array(man="555368", pin="2479", sou="358"))
        round_state = update_player(round_state, 1, tiles=player1_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        return game_state, tile_id

    def test_handle_kan__when_open_kan__should_emit_open_kan_meld(self):
        game_state, tile_id = self._create_open_kan_opportunity()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.OPEN_KAN),)),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_kan(
            game_state,
            seat=1,
            data=KanActionData(tile_id=tile_id, kan_type=KanType.OPEN),
        )
        # should resolve: open kan executed through resolution
        assert result.state.round_state.pending_call_prompt is None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.OPEN_KAN


class TestHandleKyuushuImmutable:
    def _create_kyuushu_opportunity(self) -> MahjongGameState:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # give player 0 nine or more different terminal/honor tiles
        # 9 terminals/honors: 1m, 9m, 1p, 9p, 1s, 9s, East, South, West
        # 4 filler: 2m, 3m, 4m, 5m
        kyuushu_tiles = tuple(
            TilesConverter.string_to_136_array(man="123459", pin="19", sou="19", honors="123"),
        )
        round_state = update_player(round_state, 0, tiles=kyuushu_tiles)

        # draw the 14th tile
        round_state, _tile = draw_tile(round_state)
        return game_state.model_copy(update={"round_state": round_state})

    def test_handle_kyuushu__when_valid__should_end_round_with_nine_terminals(self):
        game_state = self._create_kyuushu_opportunity()

        result = handle_kyuushu(game_state, seat=0)
        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0].result, AbortiveDrawResult)
        assert round_end_events[0].result.reason == AbortiveDrawType.NINE_TERMINALS
        assert result.state.round_state.phase == RoundPhase.FINISHED


class TestHandlePassImmutable:
    def _create_pass_prompt_state(self) -> MahjongGameState:
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, can_ron=True),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        return game_state.model_copy(update={"round_state": round_state})

    def _create_four_riichi_state(self) -> tuple[MahjongGameState, int]:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        round_state = game_state.round_state

        # set 3 players as already in riichi
        for i in range(1, 4):
            round_state = update_player(round_state, i, is_riichi=True)

        # give player 0 a tenpai hand: 123m 456m 789m 111p 3p (waiting on 2p or 4p)
        tenpai_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113"))
        round_state = update_player(round_state, 0, tiles=tenpai_tiles)

        # draw a tile for player 0
        round_state, _tile = draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[-1]

        # create discard with riichi flag (simulating riichi discard step 1)
        discards = (Discard(tile_id=tile_to_discard, is_riichi_discard=True),)
        round_state = update_player(round_state, 0, discards=discards)

        # set up pending call prompt for seat 1 (meld prompt)
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=tile_to_discard,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        return game_state, tile_to_discard

    def test_handle_pass__when_fourth_riichi__should_end_round_with_four_riichi_draw(self):
        game_state, _tile = self._create_four_riichi_state()

        # handle_pass should finalize riichi and detect four riichi
        result = handle_pass(game_state, seat=1)
        assert result.state.round_state.players[0].is_riichi is True
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0].result, AbortiveDrawResult)
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI
        assert result.state.round_state.phase == RoundPhase.FINISHED

    def test_handle_pass__when_ron_available__should_apply_temporary_furiten(self):
        game_state = self._create_pass_prompt_state()
        round_state = game_state.round_state
        original_furiten = round_state.players[1].is_temporary_furiten

        result = handle_pass(game_state, seat=1)
        # passing on ron should set temporary furiten
        assert result.state.round_state.players[1].is_temporary_furiten is True
        # original should be unchanged
        assert round_state.players[1].is_temporary_furiten == original_furiten

    def test_handle_pass__when_riichi_player__should_set_riichi_furiten(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        # set player 1 in riichi
        round_state = update_player(round_state, 1, is_riichi=True)

        # set up pending ron prompt for riichi player
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(Caller(seat=1, can_ron=True),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_pass(game_state, seat=1)
        # riichi player passing on ron should set riichi furiten
        assert result.state.round_state.players[1].is_riichi_furiten is True


class TestResolveMeldResponseImmutable:
    def _create_pon_prompt_with_response(
        self,
    ) -> MahjongGameState:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player 1 two matching tiles for pon
        tile_id = 0
        player_tiles = [tile_id, tile_id + 1, *list(new_round_state.players[1].tiles)[:-2]]
        new_round_state = update_player(new_round_state, 1, tiles=tuple(player_tiles))
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        # create prompt with pon response
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.PON),)),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_PON),),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_resolve_meld_response__when_pon__should_emit_pon_meld(self):
        game_state = self._create_pon_prompt_with_response()

        result = resolve_call_prompt(game_state)
        # should have meld event
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON


class TestCompleteAddedKanAfterChankanDeclineImmutable:
    def _create_added_kan_state(self) -> tuple[MahjongGameState, int]:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        new_round_state, _tile = draw_tile(game_state.round_state)
        player = new_round_state.players[0]

        # create a pon meld that can be upgraded
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

        # Update player with meld and fourth tile
        new_tiles = (fourth_tile, *player.tiles[:-1])
        new_round_state = update_player(new_round_state, 0, tiles=new_tiles, melds=(pon_meld,))
        game_state = game_state.model_copy(update={"round_state": new_round_state})
        return game_state, fourth_tile

    def test_complete_added_kan__should_return_new_state_with_added_kan_meld(self):
        game_state, tile_id = self._create_added_kan_state()

        new_game_state, events = complete_added_kan_after_chankan_decline(
            game_state,
            caller_seat=0,
            tile_id=tile_id,
        )
        meld_events = [e for e in events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.ADDED_KAN
        assert [m.meld_type for m in new_game_state.round_state.players[0].melds] == [FrozenMeld.SHOUMINKAN]


class TestResolveOpenKanResponseImmutable:
    def _create_open_kan_prompt(
        self,
    ) -> MahjongGameState:
        game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player 1 three matching tiles for open kan
        tile_id = 0
        player_tiles = [tile_id, tile_id + 1, tile_id + 2, *list(new_round_state.players[1].tiles)[:-3]]
        new_round_state = update_player(new_round_state, 1, tiles=tuple(player_tiles))
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        # create prompt with open kan response
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, melds=(MeldOption(call_type=MeldCallType.OPEN_KAN),)),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_KAN),),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_resolve_open_kan_response__should_emit_open_kan_meld_and_rinshan_draw(self):
        game_state = self._create_open_kan_prompt()

        result = resolve_call_prompt(game_state)
        # should have meld event
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.OPEN_KAN
        # should have draw event with tile_id and available_actions for dead wall tile
        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 1
        assert draw_events[0].tile_id is not None
        assert draw_events[0].available_actions is not None
