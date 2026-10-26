from mahjong.tile import TilesConverter

from game.logic.action_handlers import (
    handle_discard,
    handle_kan,
    handle_kyuushu,
    handle_riichi,
    handle_ron,
    handle_tsumo,
)
from game.logic.action_result import ActionResult, Refusal
from game.logic.enums import (
    AbortiveDrawType,
    AIPlayerType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldViewType,
    PromptKind,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    DiscardEvent,
    MeldEvent,
    RoundEndEvent,
)
from game.logic.game import init_game
from game.logic.round import draw_tile
from game.logic.state import (
    Caller,
    MahjongGameState,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
    AbortiveDrawResult,
    DiscardActionData,
    KanActionData,
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
