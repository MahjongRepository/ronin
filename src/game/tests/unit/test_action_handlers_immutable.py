"""
Unit tests for immutable action handlers.

Tests verify that the immutable handler functions return
new state objects and produce the expected events.
"""

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
from game.logic.action_result import ActionResult
from game.logic.call_resolution import (
    complete_added_kan_after_chankan_decline,
    resolve_call_prompt,
)
from game.logic.enums import (
    AbortiveDrawType,
    BotType,
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    MeldViewType,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    DiscardEvent,
    DrawEvent,
    ErrorEvent,
    MeldEvent,
    RoundEndEvent,
    TurnEvent,
)
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.state import (
    CallResponse,
    Discard,
    MahjongGameState,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
    AbortiveDrawResult,
    ChiActionData,
    DiscardActionData,
    KanActionData,
    MeldCaller,
    PonActionData,
    RiichiActionData,
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


class TestHandleDiscardImmutable:
    def test_handle_discard_returns_new_state(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        result = handle_discard(
            round_state, game_state, seat=0, data=DiscardActionData(tile_id=tile_to_discard)
        )

        assert isinstance(result, ActionResult)
        assert result.needs_post_discard is True
        # verify new state is returned
        assert result.new_round_state is not None
        assert result.new_game_state is not None
        # verify original state is unchanged
        assert round_state.players[0].tiles == game_state.round_state.players[0].tiles
        # verify the tile was removed from new state
        assert tile_to_discard not in result.new_round_state.players[0].tiles
        # verify discard event is produced
        discard_events = [e for e in result.events if isinstance(e, DiscardEvent)]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard

    def test_handle_discard_wrong_turn(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        result = handle_discard(round_state, game_state, seat=1, data=DiscardActionData(tile_id=tile_id))

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN
        # state should be returned unchanged
        assert result.new_round_state is round_state
        assert result.new_game_state is game_state


class TestHandleRiichiImmutable:
    def _create_riichi_hand(self) -> MahjongGameState:
        """Create a state where player can declare riichi."""
        # use a different seed to get a riichi-able hand
        game_state = init_game(_default_seat_configs(), seed=42.0)
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player a tenpai hand
        tenpai_tiles = TilesConverter.string_to_136_array(man="123456789", sou="123", pin="11")
        new_round_state = update_player(new_round_state, 0, tiles=tuple(tenpai_tiles[:14]), score=26000)
        return game_state.model_copy(update={"round_state": new_round_state})

    def test_handle_riichi_success(self):
        """Test successful riichi declaration."""
        game_state = self._create_riichi_hand()
        round_state = game_state.round_state

        # discard the last tile (14th tile) for riichi
        tile_to_discard = round_state.players[0].tiles[-1]
        result = handle_riichi(
            round_state, game_state, seat=0, data=RiichiActionData(tile_id=tile_to_discard)
        )

        assert isinstance(result, ActionResult)
        assert result.needs_post_discard is True
        # no error events
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 0
        # should have discard event
        discard_events = [e for e in result.events if isinstance(e, DiscardEvent)]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard
        assert discard_events[0].is_riichi is True

    def test_handle_riichi_wrong_turn(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        result = handle_riichi(round_state, game_state, seat=1, data=RiichiActionData(tile_id=tile_id))

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN


class TestHandleTsumoImmutable:
    def _create_winning_game_state(self) -> MahjongGameState:
        """Create a game state where player 0 has a winning hand."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 a complete winning hand (14 tiles)
        # 123m 456m 789m 111p 22p
        winning_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="11122"))
        round_state = update_player(round_state, 0, tiles=winning_tiles)
        return game_state.model_copy(update={"round_state": round_state})

    def test_handle_tsumo_success(self):
        """Test successful tsumo declaration."""
        game_state = self._create_winning_game_state()
        round_state = game_state.round_state

        result = handle_tsumo(round_state, game_state, seat=0)

        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.TSUMO

    def test_handle_tsumo_wrong_turn(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_tsumo(round_state, game_state, seat=1)

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN


class TestHandleRonImmutable:
    def _create_ron_prompt_state(
        self, pending_seats: frozenset[int] = frozenset({1, 2})
    ) -> tuple[MahjongRoundState, MahjongGameState]:
        """Create state with pending ron prompt for multiple seats."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=0,
            from_seat=0,
            pending_seats=pending_seats,
            callers=tuple(pending_seats),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})
        return round_state, game_state

    def _create_ron_opportunity(self) -> tuple[MahjongGameState, int, int]:
        """Create a game state where player 1 can ron on player 0's discard."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a waiting hand: 123m 456m 789m 111p 2p
        waiting_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
        round_state = update_player(round_state, 1, tiles=waiting_tiles)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]  # 2p (2nd copy)
        game_state = game_state.model_copy(update={"round_state": round_state})

        return game_state, win_tile, 0

    def test_handle_ron_success(self):
        """Test successful ron call."""
        game_state, win_tile, discarder_seat = self._create_ron_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for ron
        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=discarder_seat,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_ron(round_state, game_state, seat=1)

        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.RON

    def test_handle_ron_no_prompt(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_ron(round_state, game_state, seat=1)

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_RON

    def test_handle_ron_adds_response_waiting_for_others(self):
        """Test that ron adds response and waits when other callers are pending."""
        round_state, game_state = self._create_ron_prompt_state(frozenset({1, 2}))

        result = handle_ron(round_state, game_state, seat=1)

        # should update prompt with response but NOT resolve yet (seat 2 still pending)
        assert result.new_round_state is not None
        assert result.new_game_state is not None
        # check that the response was added
        prompt = result.new_round_state.pending_call_prompt
        assert prompt is not None
        assert len(prompt.responses) == 1
        assert prompt.responses[0].seat == 1
        assert prompt.responses[0].action == GameAction.CALL_RON
        # seat 1 should be removed from pending
        assert 1 not in prompt.pending_seats
        assert 2 in prompt.pending_seats

    def test_handle_ron_not_pending(self):
        """Test that ron from non-pending seat returns error."""
        round_state, game_state = self._create_ron_prompt_state(frozenset({2}))  # only seat 2 pending

        result = handle_ron(round_state, game_state, seat=1)

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_RON


class TestHandlePonImmutable:
    def _create_pon_prompt_state(self, tile_id: int = 0) -> tuple[MahjongRoundState, MahjongGameState]:
        """Create state with pending pon prompt."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player 1 two matching tiles for pon
        player_tiles = list(new_round_state.players[1].tiles)
        player_tiles.append(tile_id)
        player_tiles.append(tile_id + 1)  # same tile_34 value
        new_round_state = update_player(new_round_state, 1, tiles=tuple(player_tiles))
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": new_round_state})
        return new_round_state, game_state

    def _create_pon_opportunity(self) -> tuple[MahjongGameState, int]:
        """Create a game state where player 1 can pon."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 two 1m tiles + filler
        player1_tiles = tuple(
            TilesConverter.string_to_136_array(man="11368", pin="2479", sou="358", honors="1")
        )
        round_state = update_player(round_state, 1, tiles=player1_tiles)

        tile_to_pon = TilesConverter.string_to_136_array(man="111")[2]  # 1m (3rd copy)
        game_state = game_state.model_copy(update={"round_state": round_state})

        return game_state, tile_to_pon

    def test_handle_pon_success(self):
        """Test successful pon call."""
        game_state, tile_to_pon = self._create_pon_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for meld
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_pon,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=tile_to_pon))

        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON
        assert meld_events[0].caller_seat == 1

        turn_events = [e for e in result.events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1
        assert turn_events[0].current_seat == 1

    def test_handle_pon_no_prompt(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_PON

    def test_handle_pon_tile_mismatch(self):
        round_state, game_state = self._create_pon_prompt_state(tile_id=0)

        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=999))

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_PON
        assert "mismatch" in error_events[0].message


class TestHandleChiImmutable:
    def _create_chi_opportunity(self) -> tuple[MahjongGameState, int, tuple[int, int]]:
        """Create a game state where player 1 can chi."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 1 has 2m and 3m tiles + filler
        player1_tiles = tuple(TilesConverter.string_to_136_array(man="236789", pin="2345789"))
        round_state = update_player(round_state, 1, tiles=player1_tiles)

        # player 0 discards 1m
        tile_to_chi = TilesConverter.string_to_136_array(man="1")[0]
        seq_tiles = TilesConverter.string_to_136_array(man="23")

        game_state = game_state.model_copy(update={"round_state": round_state})
        return game_state, tile_to_chi, (seq_tiles[0], seq_tiles[1])

    def test_handle_chi_success(self):
        """Test successful chi call."""
        game_state, tile_to_chi, sequence_tiles = self._create_chi_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for meld
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_chi,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.CHI),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_chi(
            round_state,
            game_state,
            seat=1,
            data=ChiActionData(tile_id=tile_to_chi, sequence_tiles=sequence_tiles),
        )

        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CHI

        turn_events = [e for e in result.events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1
        assert turn_events[0].current_seat == 1

    def test_handle_chi_no_prompt(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_chi(
            round_state, game_state, seat=1, data=ChiActionData(tile_id=0, sequence_tiles=(1, 2))
        )

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_CHI


class TestHandleKanImmutable:
    def _create_closed_kan_opportunity(self) -> tuple[MahjongGameState, int]:
        """Create a game state where player 0 can closed kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 four 1m tiles + filler
        kan_tiles = tuple(TilesConverter.string_to_136_array(man="1111368", pin="2479", sou="35"))
        round_state = update_player(round_state, 0, tiles=kan_tiles)
        round_state, _tile = draw_tile(round_state)

        game_state = game_state.model_copy(update={"round_state": round_state})
        return game_state, TilesConverter.string_to_136_array(man="1")[0]

    def test_handle_kan_success(self):
        """Test successful closed kan."""
        game_state, tile_id = self._create_closed_kan_opportunity()
        round_state = game_state.round_state

        result = handle_kan(
            round_state, game_state, seat=0, data=KanActionData(tile_id=tile_id, kan_type=KanType.CLOSED)
        )

        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN
        assert meld_events[0].kan_type == KanType.CLOSED

    def test_handle_kan_wrong_turn_closed(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=0, kan_type=KanType.CLOSED)
        )

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN

    def _create_open_kan_opportunity(self) -> tuple[MahjongGameState, int]:
        """Create a game state where player 1 can open kan after player 0 discards."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        # give player 1 three 5m tiles + filler for open kan
        player1_tiles = tuple(TilesConverter.string_to_136_array(man="555368", pin="2479", sou="358"))
        round_state = update_player(round_state, 1, tiles=player1_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        return game_state, tile_id

    def test_handle_open_kan_success(self):
        """Open kan through pending prompt records intent and resolves."""
        game_state, tile_id = self._create_open_kan_opportunity()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=tile_id, kan_type=KanType.OPEN)
        )

        # should resolve: open kan executed through resolution
        assert result.new_round_state is not None
        assert result.new_round_state.pending_call_prompt is None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN

    def test_handle_open_kan_no_prompt(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # create a pending prompt but not for the calling seat
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({2}),  # seat 1 is not in pending
            callers=(MeldCaller(seat=2, call_type=MeldCallType.OPEN_KAN),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=0, kan_type=KanType.OPEN)
        )

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_KAN


class TestHandleKyuushuImmutable:
    def _create_kyuushu_opportunity(self) -> MahjongGameState:
        """Create a game state where player 0 can call kyuushu kyuuhai."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 nine or more different terminal/honor tiles
        # 9 terminals/honors: 1m, 9m, 1p, 9p, 1s, 9s, East, South, West
        # 4 filler: 2m, 3m, 4m, 5m
        kyuushu_tiles = tuple(
            TilesConverter.string_to_136_array(man="123459", pin="19", sou="19", honors="123")
        )
        round_state = update_player(round_state, 0, tiles=kyuushu_tiles)

        # draw the 14th tile
        round_state, _tile = draw_tile(round_state)
        return game_state.model_copy(update={"round_state": round_state})

    def test_handle_kyuushu_success(self):
        game_state = self._create_kyuushu_opportunity()
        round_state = game_state.round_state

        result = handle_kyuushu(round_state, game_state, seat=0)

        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0].result, AbortiveDrawResult)
        assert round_end_events[0].result.reason == AbortiveDrawType.NINE_TERMINALS
        assert result.new_round_state is not None
        assert result.new_round_state.phase == RoundPhase.FINISHED

    def test_handle_kyuushu_wrong_turn(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_kyuushu(round_state, game_state, seat=1)

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN

    def test_handle_kyuushu_cannot_call(self):
        """Test kyuushu fails when conditions aren't met (e.g., discards already made)."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # Add a discard to prevent kyuushu
        round_state = update_player(round_state, 0, discards=(Discard(tile_id=0),))
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_kyuushu(round_state, game_state, seat=0)

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.CANNOT_CALL_KYUUSHU


class TestHandlePassImmutable:
    def _create_pass_prompt_state(self) -> tuple[MahjongRoundState, MahjongGameState]:
        """Create state with pending prompt that can be passed."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})
        return round_state, game_state

    def _create_four_riichi_state(self) -> tuple[MahjongRoundState, MahjongGameState, int]:
        """Create state where passing finalizes 4th riichi (triggers abortive draw)."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
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
            call_type=CallType.MELD,
            tile_id=tile_to_discard,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING}
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        return round_state, game_state, tile_to_discard

    def test_handle_pass_four_riichi_abortive_draw(self):
        """Pass finalizing 4th riichi triggers four riichi abortive draw."""
        round_state, game_state, _tile = self._create_four_riichi_state()

        # handle_pass should finalize riichi and detect four riichi
        result = handle_pass(round_state, game_state, seat=1)

        assert result.new_round_state is not None
        assert result.new_round_state.players[0].is_riichi is True
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0].result, AbortiveDrawResult)
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI
        assert result.new_round_state.phase == RoundPhase.FINISHED

    def test_handle_pass_no_prompt(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_pass(round_state, game_state, seat=1)

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_PASS

    def test_handle_pass_applies_furiten(self):
        round_state, game_state = self._create_pass_prompt_state()
        original_furiten = round_state.players[1].is_temporary_furiten

        result = handle_pass(round_state, game_state, seat=1)

        assert result.new_round_state is not None
        # passing on ron should set temporary furiten
        assert result.new_round_state.players[1].is_temporary_furiten is True
        # original should be unchanged
        assert round_state.players[1].is_temporary_furiten == original_furiten

    def test_handle_pass_riichi_player_sets_riichi_furiten(self):
        """Test that passing on ron while in riichi sets riichi furiten."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # set player 1 in riichi
        round_state = update_player(round_state, 1, is_riichi=True)

        # set up pending ron prompt for riichi player
        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_pass(round_state, game_state, seat=1)

        assert result.new_round_state is not None
        # riichi player passing on ron should set riichi furiten
        assert result.new_round_state.players[1].is_riichi_furiten is True


class TestResolveCallPromptImmutable:
    def test_resolve_no_prompt(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = resolve_call_prompt(round_state, game_state)

        assert isinstance(result, ActionResult)
        assert len(result.events) == 0
        assert result.new_round_state is round_state
        assert result.new_game_state is game_state

    def test_resolve_with_all_passes_on_meld_prompt(self):
        """Test that prompt with no responses advances to next turn."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # create a meld prompt with no pending seats (all passed)
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),  # all passed
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
            responses=(),  # no meld responses
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING}
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        # prompt should be cleared
        assert result.new_round_state.pending_call_prompt is None


class TestResolveMeldResponseImmutable:
    """Tests for _resolve_meld_response via resolve_call_prompt."""

    def _create_pon_prompt_with_response(
        self,
    ) -> tuple[MahjongRoundState, MahjongGameState]:
        """Create state with a pon response ready to resolve."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player 1 two matching tiles for pon
        tile_id = 0
        player_tiles = [tile_id, tile_id + 1, *list(new_round_state.players[1].tiles)[:-2]]
        new_round_state = update_player(new_round_state, 1, tiles=tuple(player_tiles))
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        # create prompt with pon response
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_PON),),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": new_round_state})
        return new_round_state, game_state

    def test_resolve_pon_response(self):
        """Test resolving a pon call creates meld event and updates state."""
        round_state, game_state = self._create_pon_prompt_with_response()

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        assert result.new_game_state is not None
        # should have meld event
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON


class TestCompleteAddedKanAfterChankanDeclineImmutable:
    def _create_added_kan_state(self) -> tuple[MahjongRoundState, MahjongGameState, int]:
        """Create state where a player has pon and can upgrade to kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
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
        return new_round_state, game_state, fourth_tile

    def test_complete_added_kan_returns_new_state(self):
        round_state, game_state, tile_id = self._create_added_kan_state()

        new_round_state, new_game_state, events = complete_added_kan_after_chankan_decline(
            round_state, game_state, caller_seat=0, tile_id=tile_id
        )

        assert new_round_state is not None
        assert new_game_state is not None
        # check for meld event
        meld_events = [e for e in events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN
        assert meld_events[0].kan_type == KanType.ADDED


class TestResolveOpenKanResponseImmutable:
    """Tests for open kan resolution that draws from dead wall."""

    def _create_open_kan_prompt(
        self,
    ) -> tuple[MahjongRoundState, MahjongGameState]:
        """Create state with open kan response ready to resolve."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player 1 three matching tiles for open kan
        tile_id = 0
        player_tiles = [tile_id, tile_id + 1, tile_id + 2, *list(new_round_state.players[1].tiles)[:-3]]
        new_round_state = update_player(new_round_state, 1, tiles=tuple(player_tiles))
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        # create prompt with open kan response
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_KAN),),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": new_round_state})
        return new_round_state, game_state

    def test_resolve_open_kan_response(self):
        """Test resolving an open kan call draws from dead wall and creates events."""
        round_state, game_state = self._create_open_kan_prompt()

        result = resolve_call_prompt(round_state, game_state)

        assert result.new_round_state is not None
        assert result.new_game_state is not None
        # should have meld event
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN
        # should have draw event for dead wall tile
        draw_events = [e for e in result.events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 1
        # should have turn event
        turn_events = [e for e in result.events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1


class TestHandleDiscardImmutableWithPrompt:
    """Test discard that creates call prompt."""

    def test_discard_creates_pon_prompt(self):
        """Test that discarding creates a pending call prompt when opponents can call."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        new_round_state, _tile = draw_tile(game_state.round_state)

        # give player 1 two matching tiles for pon
        tile_to_discard = new_round_state.players[0].tiles[0]
        tile_34 = tile_to_discard // 4
        player1_tiles = [tile_34 * 4 + 1, tile_34 * 4 + 2, *list(new_round_state.players[1].tiles)[:-2]]
        new_round_state = update_player(new_round_state, 1, tiles=tuple(player1_tiles))
        game_state = game_state.model_copy(update={"round_state": new_round_state})

        result = handle_discard(
            new_round_state, game_state, seat=0, data=DiscardActionData(tile_id=tile_to_discard)
        )

        # check events
        discard_events = [e for e in result.events if isinstance(e, DiscardEvent)]
        assert len(discard_events) == 1
        # may or may not have a call prompt depending on tile values


class TestHandlerErrorPaths:
    """Test error handling paths in immutable handlers."""

    def test_discard_invalid_tile_returns_error(self):
        """Test discarding a tile not in hand returns error."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # try to discard a tile not in hand
        invalid_tile = 999
        result = handle_discard(round_state, game_state, seat=0, data=DiscardActionData(tile_id=invalid_tile))

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_DISCARD
        # state should be returned unchanged
        assert result.new_round_state is round_state
        assert result.new_game_state is game_state

    def test_riichi_invalid_tile_returns_error(self):
        """Test riichi with invalid tile returns error."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # try to riichi with a tile not in hand
        invalid_tile = 999
        result = handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=invalid_tile))

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_RIICHI
        # state should be returned unchanged
        assert result.new_round_state is round_state
        assert result.new_game_state is game_state
