"""
Unit tests for action handlers.
"""

from mahjong.meld import Meld as MahjongMeld
from mahjong.tile import TilesConverter

from game.logic.action_handlers import (
    ActionResult,
    complete_added_kan_after_chankan_decline,
    handle_chi,
    handle_discard,
    handle_kan,
    handle_kyuushu,
    handle_pass,
    handle_pon,
    handle_riichi,
    handle_ron,
    handle_tsumo,
    resolve_call_prompt,
)
from game.logic.enums import AbortiveDrawType, BotType, CallType, KanType, MeldCallType, MeldViewType
from game.logic.game import init_game
from game.logic.round import discard_tile, draw_tile
from game.logic.state import MahjongGameState, PendingCallPrompt, RoundPhase
from game.logic.types import (
    AbortiveDrawResult,
    ChiActionData,
    DiscardActionData,
    KanActionData,
    MeldCaller,
    PonActionData,
    RiichiActionData,
    RonActionData,
    SeatConfig,
)
from game.messaging.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    ErrorEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    TurnEvent,
)


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", bot_type=BotType.TSUMOGIRI),
    ]


class TestHandleDiscard:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        draw_tile(game_state.round_state)
        return game_state

    def test_handle_discard_success(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        result = handle_discard(
            round_state, game_state, seat=0, data=DiscardActionData(tile_id=tile_to_discard)
        )

        assert isinstance(result, ActionResult)
        assert result.needs_post_discard is True
        discard_events = [e for e in result.events if isinstance(e, DiscardEvent)]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard

    def test_handle_discard_wrong_turn(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        result = handle_discard(round_state, game_state, seat=1, data=DiscardActionData(tile_id=tile_id))

        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "not_your_turn"


class TestHandleRiichi:
    def _create_tempai_game_state(self) -> MahjongGameState:
        """Create a game state where player 0 is in tempai."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # manually set player 0 to have a tempai hand
        # 123m 456m 789m 111p 3p
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1113")
        draw_tile(round_state)
        return game_state

    def test_handle_riichi_success(self):
        game_state = self._create_tempai_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[-1]

        result = handle_riichi(
            round_state, game_state, seat=0, data=RiichiActionData(tile_id=tile_to_discard)
        )

        assert isinstance(result, ActionResult)
        assert result.needs_post_discard is True

    def test_handle_riichi_wrong_turn(self):
        game_state = self._create_tempai_game_state()
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        result = handle_riichi(round_state, game_state, seat=1, data=RiichiActionData(tile_id=tile_id))

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "not_your_turn"

    def test_handle_riichi_not_tempai(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[0]

        result = handle_riichi(
            round_state, game_state, seat=0, data=RiichiActionData(tile_id=tile_to_discard)
        )

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_riichi"


class TestHandleTsumo:
    def _create_winning_game_state(self) -> MahjongGameState:
        """Create a game state where player 0 has a winning hand."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 a complete winning hand (14 tiles)
        # 123m 456m 789m 111p 22p
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="11122")
        return game_state

    def test_handle_tsumo_success(self):
        game_state = self._create_winning_game_state()
        round_state = game_state.round_state

        result = handle_tsumo(round_state, game_state, seat=0)

        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == "tsumo"

    def test_handle_tsumo_wrong_turn(self):
        game_state = self._create_winning_game_state()
        round_state = game_state.round_state

        result = handle_tsumo(round_state, game_state, seat=1)

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "not_your_turn"

    def test_handle_tsumo_no_winning_hand(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        draw_tile(round_state)

        result = handle_tsumo(round_state, game_state, seat=0)

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_tsumo"


class TestHandleRon:
    def _create_ron_opportunity(self) -> tuple[MahjongGameState, int, int]:
        """Create a game state where player 1 can ron on player 0's discard."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a waiting hand: 123m 456m 789m 111p 2p
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]  # 2p (2nd copy)
        round_state.players[0].tiles.append(win_tile)
        round_state.current_player_seat = 0

        return game_state, win_tile, 0

    def test_handle_ron_success(self):
        game_state, win_tile, discarder_seat = self._create_ron_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for ron
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=discarder_seat,
            pending_seats={1},
            callers=[1],
        )

        result = handle_ron(
            round_state, game_state, seat=1, data=RonActionData(tile_id=win_tile, from_seat=discarder_seat)
        )

        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == "ron"


class TestHandlePon:
    def _create_pon_opportunity(self) -> tuple[MahjongGameState, int]:
        """Create a game state where player 1 can pon."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 two 1m tiles + filler
        round_state.players[1].tiles = TilesConverter.string_to_136_array(
            man="11368", pin="2479", sou="358", honors="1"
        )

        tile_to_pon = TilesConverter.string_to_136_array(man="111")[2]  # 1m (3rd copy)
        round_state.players[0].tiles.append(tile_to_pon)
        round_state.current_player_seat = 0

        return game_state, tile_to_pon

    def test_handle_pon_success(self):
        game_state, tile_to_pon = self._create_pon_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for meld
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_pon,
            from_seat=0,
            pending_seats={1},
            callers=[
                MeldCaller(seat=1, call_type=MeldCallType.PON),
            ],
        )

        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=tile_to_pon))

        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON
        assert meld_events[0].caller_seat == 1

        turn_events = [e for e in result.events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1
        assert turn_events[0].current_seat == 1


class TestHandleChi:
    def _create_chi_opportunity(self) -> tuple[MahjongGameState, int, list[int]]:
        """Create a game state where player 1 can chi."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 1 has 2m and 3m tiles + filler
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="236789", pin="2345789")

        # player 0 discards 1m
        round_state.current_player_seat = 0
        tile_to_chi = TilesConverter.string_to_136_array(man="1")[0]

        return game_state, tile_to_chi, TilesConverter.string_to_136_array(man="23")

    def test_handle_chi_success(self):
        game_state, tile_to_chi, sequence_tiles = self._create_chi_opportunity()
        round_state = game_state.round_state

        # set up pending call prompt for meld
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_chi,
            from_seat=0,
            pending_seats={1},
            callers=[
                MeldCaller(seat=1, call_type=MeldCallType.CHI),
            ],
        )

        result = handle_chi(
            round_state,
            game_state,
            seat=1,
            data=ChiActionData(tile_id=tile_to_chi, sequence_tiles=(sequence_tiles[0], sequence_tiles[1])),
        )

        assert isinstance(result, ActionResult)
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CHI

        turn_events = [e for e in result.events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1
        assert turn_events[0].current_seat == 1


class TestHandleKan:
    def _create_closed_kan_opportunity(self) -> tuple[MahjongGameState, int]:
        """Create a game state where player 0 can closed kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 four 1m tiles + filler
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="1111368", pin="2479", sou="35")
        draw_tile(round_state)

        return game_state, TilesConverter.string_to_136_array(man="1")[0]

    def test_handle_kan_success(self):
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


class TestHandleKyuushu:
    def _create_kyuushu_opportunity(self) -> MahjongGameState:
        """Create a game state where player 0 can call kyuushu kyuuhai."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 nine or more different terminal/honor tiles
        # 9 terminals/honors: 1m, 9m, 1p, 9p, 1s, 9s, East, South, West
        # 4 filler: 2m, 3m, 4m, 5m
        round_state.players[0].tiles = TilesConverter.string_to_136_array(
            man="123459", pin="19", sou="19", honors="123"
        )

        # draw the 14th tile
        draw_tile(round_state)

        return game_state

    def test_handle_kyuushu_success(self):
        game_state = self._create_kyuushu_opportunity()
        round_state = game_state.round_state

        result = handle_kyuushu(round_state, game_state, seat=0)

        assert isinstance(result, ActionResult)
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0].result, AbortiveDrawResult)
        assert round_end_events[0].result.reason == AbortiveDrawType.NINE_TERMINALS
        assert round_state.phase == RoundPhase.FINISHED

    def test_handle_kyuushu_wrong_turn(self):
        game_state = self._create_kyuushu_opportunity()
        round_state = game_state.round_state

        result = handle_kyuushu(round_state, game_state, seat=1)

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "not_your_turn"

    def test_handle_kyuushu_not_eligible(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        draw_tile(round_state)

        result = handle_kyuushu(round_state, game_state, seat=0)

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "cannot_call_kyuushu"


class TestHandlePass:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        return init_game(_default_seat_configs(), seed=12345.0)

    def test_handle_pass_no_pending_prompt_returns_empty(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        draw_tile(round_state)

        result = handle_pass(round_state, game_state, seat=0)

        assert isinstance(result, ActionResult)
        assert result.events == []

    def test_handle_pass_after_discard_advances_turn(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        draw_tile(round_state)

        # simulate a discard leaving current player with 13 tiles
        tile_to_discard = round_state.players[0].tiles[0]
        discard_tile(round_state, 0, tile_to_discard)

        # set up pending call prompt for seat 1 (meld prompt)
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_discard,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        initial_seat = round_state.current_player_seat
        handle_pass(round_state, game_state, seat=1)

        # turn should advance after pass (resolution triggers advance_turn)
        assert round_state.current_player_seat == (initial_seat + 1) % 4


class TestActionResult:
    def test_action_result_default_needs_post_discard(self):
        result = ActionResult([])
        assert result.needs_post_discard is False

    def test_action_result_with_needs_post_discard(self):
        result = ActionResult([], needs_post_discard=True)
        assert result.needs_post_discard is True


class TestHandlePonError:
    def test_handle_pon_invalid_tile_returns_error(self):
        """Pon with tile the player doesn't have matching copies of returns an error."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        round_state.current_player_seat = 0

        # player 1 has no matching tiles for Chun (red dragon)
        chun_tile = TilesConverter.string_to_136_array(honors="7")[0]
        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=chun_tile))

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_pon"


class TestHandleChiError:
    def test_handle_chi_invalid_sequence_returns_error(self):
        """Chi with tiles the player doesn't have returns an error."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        round_state.current_player_seat = 0

        # player 1 doesn't have these sequence tiles (1m, 2m, 3m)
        man_tiles = TilesConverter.string_to_136_array(man="123")
        result = handle_chi(
            round_state,
            game_state,
            seat=1,
            data=ChiActionData(tile_id=man_tiles[0], sequence_tiles=(man_tiles[1], man_tiles[2])),
        )

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_chi"


class TestHandleKanError:
    def test_handle_kan_invalid_tile_returns_error(self):
        """Kan with tile the player doesn't have 4 copies of returns an error."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        draw_tile(round_state)

        # player 0 doesn't have 4 copies of Chun (red dragon)
        chun_tile = TilesConverter.string_to_136_array(honors="7")[0]
        result = handle_kan(
            round_state, game_state, seat=0, data=KanActionData(tile_id=chun_tile, kan_type=KanType.CLOSED)
        )

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_kan"


class TestHandleRonValueError:
    """Tests handle_ron error path when process_ron_call raises ValueError."""

    def test_handle_ron_no_pending_prompt_returns_error(self):
        """Calling handle_ron without a pending call prompt returns an error."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        result = handle_ron(round_state, game_state, seat=1, data=RonActionData(tile_id=tile_id, from_seat=0))

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_ron"
        assert error_events[0].message == "no pending call prompt"


class TestHandleKanFourKansAbort:
    """Tests handle_kan when four kans abort triggers during kan processing."""

    def test_handle_kan_four_kans_abort(self):
        """Closed kan triggering four kans abortive draw returns round end event."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # three players each have one kan meld
        round_state.players[1].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="1111"),
                opened=True,
                who=1,
                from_who=0,
            )
        ]
        round_state.players[2].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="2222"),
                opened=True,
                who=2,
                from_who=0,
            )
        ]
        round_state.players[3].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="3333"),
                opened=True,
                who=3,
                from_who=0,
            )
        ]

        # player 0 has four 4m tiles for closed kan + filler
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="4444678", pin="123456")
        draw_tile(round_state)
        round_state.current_player_seat = 0

        kan_tile = TilesConverter.string_to_136_array(man="4")[0]
        result = handle_kan(
            round_state, game_state, seat=0, data=KanActionData(tile_id=kan_tile, kan_type=KanType.CLOSED)
        )

        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS
        assert round_state.phase == RoundPhase.FINISHED


class TestHandleKanChankanPrompt:
    """Tests handle_kan returning chankan prompt during added kan."""

    def test_handle_kan_chankan_prompt(self):
        """Added kan triggers chankan prompt when opponent is waiting on the tile."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 0 has pon of 3p and the 4th 3p in hand
        pin_3_tiles = TilesConverter.string_to_136_array(pin="3333")
        pon_meld = MahjongMeld(
            meld_type=MahjongMeld.PON,
            tiles=pin_3_tiles[:3],
            opened=True,
            called_tile=pin_3_tiles[2],
            who=0,
            from_who=1,
        )
        round_state.players[0].melds = [pon_meld]
        round_state.players[0].tiles = [
            pin_3_tiles[3],
            *TilesConverter.string_to_136_array(man="123456789"),
        ]
        round_state.players_with_open_hands = [0]
        round_state.current_player_seat = 0
        draw_tile(round_state)

        # player 1 waiting for 3p: 123m 456m 789m 12p 55p
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")

        result = handle_kan(
            round_state,
            game_state,
            seat=0,
            data=KanActionData(tile_id=pin_3_tiles[3], kan_type=KanType.ADDED),
        )

        call_prompts = [
            e for e in result.events if isinstance(e, CallPromptEvent) and e.call_type == CallType.CHANKAN
        ]
        assert len(call_prompts) == 1


class TestHandlePassRiichiFinalization:
    """Tests handle_pass finalizing a pending riichi declaration."""

    def test_handle_pass_finalizes_riichi(self):
        """Pass after riichi discard finalizes riichi declaration."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 a tempai hand: 123m 456m 789m 111p 3p
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1113")

        # draw a tile for player 0
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[-1]

        # perform the riichi discard (step 1 only: marks the discard as riichi)
        discard_tile(round_state, 0, tile_to_discard, is_riichi=True)

        # player 0 now has 13 tiles with last discard marked as riichi
        assert len(round_state.players[0].tiles) == 13
        assert round_state.players[0].discards[-1].is_riichi_discard is True
        assert round_state.players[0].is_riichi is False  # not yet finalized

        # set up pending call prompt for seat 1 (meld prompt)
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_discard,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        # handle_pass should finalize the riichi
        result = handle_pass(round_state, game_state, seat=1)

        riichi_events = [e for e in result.events if isinstance(e, RiichiDeclaredEvent)]
        assert len(riichi_events) == 1
        assert round_state.players[0].is_riichi is True

    def test_handle_pass_four_riichi_abortive_draw(self):
        """Pass finalizing 4th riichi triggers four riichi abortive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # set 3 players as already in riichi
        for i in range(1, 4):
            round_state.players[i].is_riichi = True

        # give player 0 a tempai hand: 123m 456m 789m 111p 3p
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1113")

        # draw a tile for player 0
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[-1]

        # perform the riichi discard (step 1 only: marks the discard as riichi)
        discard_tile(round_state, 0, tile_to_discard, is_riichi=True)

        # set up pending call prompt for seat 1 (meld prompt)
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_discard,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        # handle_pass should finalize riichi and detect four riichi
        result = handle_pass(round_state, game_state, seat=1)

        assert round_state.players[0].is_riichi is True
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI
        assert round_state.phase == RoundPhase.FINISHED


class TestCompleteAddedKanAfterChankanDecline:
    """Tests the complete_added_kan_after_chankan_decline function."""

    def test_complete_added_kan(self):
        """Complete added kan after chankan declined produces meld and draw events."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 0 has pon of 1m and the 4th 1m in hand
        man_1_tiles = TilesConverter.string_to_136_array(man="1111")
        pon_meld = MahjongMeld(
            meld_type=MahjongMeld.PON,
            tiles=man_1_tiles[:3],
            opened=True,
            called_tile=man_1_tiles[2],
            who=0,
            from_who=1,
        )
        round_state.players[0].melds = [pon_meld]
        round_state.players[0].tiles = [
            man_1_tiles[3],
            *TilesConverter.string_to_136_array(man="368", pin="2479", sou="358", honors="14"),
        ]
        round_state.players_with_open_hands = [0]
        round_state.current_player_seat = 0

        events = complete_added_kan_after_chankan_decline(
            round_state, game_state, caller_seat=0, tile_id=man_1_tiles[3]
        )

        meld_events = [e for e in events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN
        assert meld_events[0].kan_type == KanType.ADDED

        # should also have draw and turn events (no four kans abort)
        draw_events = [e for e in events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 1
        turn_events = [e for e in events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1

    def test_complete_added_kan_four_kans_abort(self):
        """Complete added kan triggering four kans abort returns round end event."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # three players each have one kan meld
        round_state.players[1].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="2222"),
                opened=True,
                who=1,
                from_who=0,
            )
        ]
        round_state.players[2].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="3333"),
                opened=True,
                who=2,
                from_who=0,
            )
        ]
        round_state.players[3].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="4444"),
                opened=True,
                who=3,
                from_who=0,
            )
        ]

        # player 0 has pon of 1m and the 4th 1m tile
        man_1_tiles = TilesConverter.string_to_136_array(man="1111")
        pon_meld = MahjongMeld(
            meld_type=MahjongMeld.PON,
            tiles=man_1_tiles[:3],
            opened=True,
            called_tile=man_1_tiles[2],
            who=0,
            from_who=1,
        )
        round_state.players[0].melds = [pon_meld]
        round_state.players[0].tiles = [
            man_1_tiles[3],
            *TilesConverter.string_to_136_array(man="678", pin="123456789"),
        ]
        round_state.players_with_open_hands = [0]
        round_state.current_player_seat = 0

        events = complete_added_kan_after_chankan_decline(
            round_state, game_state, caller_seat=0, tile_id=man_1_tiles[3]
        )

        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS
        assert round_state.phase == RoundPhase.FINISHED


class TestResolveCallPrompt:
    """Tests for the resolve_call_prompt function and multi-caller resolution."""

    def test_resolve_single_pass_advances_turn(self):
        """Single caller passing resolves prompt and advances turn."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        draw_tile(round_state)

        tile_to_discard = round_state.players[0].tiles[0]
        discard_tile(round_state, 0, tile_to_discard)

        # set up pending meld prompt for seat 1
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_discard,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        initial_seat = round_state.current_player_seat
        handle_pass(round_state, game_state, seat=1)

        # prompt should be resolved and turn advanced
        assert round_state.pending_call_prompt is None
        assert round_state.current_player_seat == (initial_seat + 1) % 4

    def test_resolve_multi_caller_all_pass(self):
        """Multiple callers all passing resolves prompt and advances turn."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        draw_tile(round_state)

        tile_to_discard = round_state.players[0].tiles[0]
        discard_tile(round_state, 0, tile_to_discard)

        # set up pending meld prompt for seats 1 and 2
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_discard,
            from_seat=0,
            pending_seats={1, 2},
            callers=[
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=2, call_type=MeldCallType.CHI),
            ],
        )

        # first pass: seat 1 passes
        handle_pass(round_state, game_state, seat=1)
        # prompt should still be pending (seat 2 hasn't responded)
        assert round_state.pending_call_prompt is not None
        assert round_state.pending_call_prompt.pending_seats == {2}

        initial_seat = round_state.current_player_seat

        # second pass: seat 2 passes -> resolves
        handle_pass(round_state, game_state, seat=2)
        assert round_state.pending_call_prompt is None
        assert round_state.current_player_seat == (initial_seat + 1) % 4

    def test_resolve_pon_with_pending_prompt(self):
        """Pon call through pending prompt executes correctly."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 two 1m tiles + filler
        round_state.players[1].tiles = TilesConverter.string_to_136_array(
            man="11368", pin="2479", sou="358", honors="1"
        )

        tile_to_pon = TilesConverter.string_to_136_array(man="111")[2]  # 1m (3rd copy)
        round_state.players[0].tiles.append(tile_to_pon)
        round_state.current_player_seat = 0

        # set up pending meld prompt for seat 1 only
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_to_pon,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=tile_to_pon))

        # should resolve immediately since only one caller
        assert round_state.pending_call_prompt is None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON
        turn_events = [e for e in result.events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1

    def test_resolve_ron_with_pending_prompt(self):
        """Ron call through pending prompt executes correctly."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a waiting hand: 123m 456m 789m 111p 2p
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")
        win_tile = TilesConverter.string_to_136_array(pin="22")[1]
        round_state.players[0].tiles.append(win_tile)
        round_state.current_player_seat = 0

        # set up pending ron prompt for seat 1
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats={1},
            callers=[1],
        )

        result = handle_ron(
            round_state, game_state, seat=1, data=RonActionData(tile_id=win_tile, from_seat=0)
        )

        assert round_state.pending_call_prompt is None
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == "ron"

    def test_pon_beats_chi_in_resolution(self):
        """When both pon and chi are recorded, pon wins by priority."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        # give player 1 tiles for pon: two 5m tiles + filler
        round_state.players[1].tiles = TilesConverter.string_to_136_array(
            man="55368", pin="2479", sou="358", honors="1"
        )
        # give player 2 tiles for chi: 6m 7m + filler (but kamicha check not relevant here,
        # we're testing resolution priority)
        round_state.players[2].tiles = TilesConverter.string_to_136_array(man="67", pin="234567", sou="23589")

        round_state.current_player_seat = 0

        # set up pending meld prompt for seats 1 (pon) and 2 (chi)
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1, 2},
            callers=[
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=2, call_type=MeldCallType.CHI),
            ],
        )

        seq_tiles = TilesConverter.string_to_136_array(man="67")

        # seat 2 responds with chi first
        handle_chi(
            round_state,
            game_state,
            seat=2,
            data=ChiActionData(tile_id=tile_id, sequence_tiles=(seq_tiles[0], seq_tiles[1])),
        )
        # still waiting for seat 1
        assert round_state.pending_call_prompt is not None

        # seat 1 responds with pon
        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=tile_id))

        # pon should win (pon has higher priority than chi)
        assert round_state.pending_call_prompt is None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.PON
        assert meld_events[0].caller_seat == 1

    def test_handle_pass_chankan_prompt_applies_furiten(self):
        """Passing on chankan prompt applies temporary furiten."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 0 has pon of 3p and the 4th 3p in hand for added kan
        pin_3_tiles = TilesConverter.string_to_136_array(pin="3333")
        pon_meld = MahjongMeld(
            meld_type=MahjongMeld.PON,
            tiles=pin_3_tiles[:3],
            opened=True,
            called_tile=pin_3_tiles[2],
            who=0,
            from_who=1,
        )
        round_state.players[0].melds = [pon_meld]
        round_state.players[0].tiles = [
            pin_3_tiles[3],
            *TilesConverter.string_to_136_array(man="123456789"),
        ]
        round_state.players_with_open_hands = [0]
        round_state.current_player_seat = 0

        # set up chankan pending prompt for seat 1
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=pin_3_tiles[3],
            from_seat=0,
            pending_seats={1},
            callers=[1],
        )

        # player 1 is in riichi
        round_state.players[1].is_riichi = True

        handle_pass(round_state, game_state, seat=1)

        assert round_state.players[1].is_temporary_furiten is True
        assert round_state.players[1].is_riichi_furiten is True

    def test_handle_pass_not_caller_returns_empty(self):
        """Passing when not a pending caller returns empty events."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="1")[0]

        # set up pending prompt for seat 1, but seat 3 passes
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        result = handle_pass(round_state, game_state, seat=3)

        assert result.events == []
        # prompt should still be pending for seat 1
        assert round_state.pending_call_prompt is not None
        assert 1 in round_state.pending_call_prompt.pending_seats

    def test_resolve_prompt_none_returns_empty(self):
        """resolve_call_prompt with no pending prompt returns empty result."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        result = resolve_call_prompt(round_state, game_state)

        assert result.events == []

    def test_resolve_triple_ron_abortive_draw(self):
        """Three ron responses trigger triple ron abortive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give players 1, 2, 3 waiting hands: 123m 456m 789m 111p 2p
        for seat in [1, 2, 3]:
            round_state.players[seat].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]
        round_state.players[0].tiles.append(win_tile)
        round_state.current_player_seat = 0

        # set up pending ron prompt for all three seats
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats={1, 2, 3},
            callers=[1, 2, 3],
        )

        # seats 1 and 2 call ron
        handle_ron(round_state, game_state, seat=1, data=RonActionData(tile_id=win_tile, from_seat=0))
        handle_ron(round_state, game_state, seat=2, data=RonActionData(tile_id=win_tile, from_seat=0))

        # seat 3 calls ron -> triple ron
        result = handle_ron(
            round_state, game_state, seat=3, data=RonActionData(tile_id=win_tile, from_seat=0)
        )

        assert round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.TRIPLE_RON

    def test_handle_ron_waiting_for_other_callers(self):
        """Ron call with other pending callers returns empty events (waiting)."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]

        # set up pending ron prompt for seats 1 and 2
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats={1, 2},
            callers=[1, 2],
        )

        # seat 1 calls ron, but seat 2 hasn't responded yet
        result = handle_ron(
            round_state, game_state, seat=1, data=RonActionData(tile_id=win_tile, from_seat=0)
        )

        assert result.events == []
        assert round_state.pending_call_prompt is not None
        assert round_state.pending_call_prompt.pending_seats == {2}

    def test_handle_pon_tile_id_mismatch(self):
        """Pon with mismatched tile_id returns error when pending prompt exists."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        correct_tile = TilesConverter.string_to_136_array(man="1")[0]
        wrong_tile = TilesConverter.string_to_136_array(man="2")[0]

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=correct_tile,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=wrong_tile))

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_pon"
        assert error_events[0].message == "tile_id mismatch"

    def test_handle_pon_waiting_for_other_callers(self):
        """Pon call with other pending callers returns empty events (waiting)."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1, 2},
            callers=[
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=2, call_type=MeldCallType.CHI),
            ],
        )

        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=tile_id))

        assert result.events == []
        assert round_state.pending_call_prompt is not None
        assert round_state.pending_call_prompt.pending_seats == {2}

    def test_handle_chi_tile_id_mismatch(self):
        """Chi with mismatched tile_id returns error when pending prompt exists."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        correct_tile = TilesConverter.string_to_136_array(man="1")[0]
        wrong_tile = TilesConverter.string_to_136_array(man="2")[0]
        seq = TilesConverter.string_to_136_array(man="23")

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=correct_tile,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.CHI)],
        )

        result = handle_chi(
            round_state,
            game_state,
            seat=1,
            data=ChiActionData(tile_id=wrong_tile, sequence_tiles=(seq[0], seq[1])),
        )

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_chi"
        assert error_events[0].message == "tile_id mismatch"

    def test_handle_chi_resolves_as_sole_caller(self):
        """Chi call as sole caller resolves prompt immediately."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]
        seq = TilesConverter.string_to_136_array(man="67")

        # give player 1 tiles for chi: 6m 7m + filler
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="67", pin="234567", sou="23589")
        round_state.current_player_seat = 0

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.CHI)],
        )

        result = handle_chi(
            round_state,
            game_state,
            seat=1,
            data=ChiActionData(tile_id=tile_id, sequence_tiles=(seq[0], seq[1])),
        )

        assert round_state.pending_call_prompt is None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.CHI

    def test_handle_chi_waiting_for_other_callers(self):
        """Chi call with other pending callers returns empty events (waiting)."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]
        seq = TilesConverter.string_to_136_array(man="67")

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1, 2},
            callers=[
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=2, call_type=MeldCallType.CHI),
            ],
        )

        result = handle_chi(
            round_state,
            game_state,
            seat=2,
            data=ChiActionData(tile_id=tile_id, sequence_tiles=(seq[0], seq[1])),
        )

        assert result.events == []
        assert round_state.pending_call_prompt is not None
        assert round_state.pending_call_prompt.pending_seats == {1}

    def test_handle_open_kan_call_response(self):
        """Open kan through pending prompt records intent and resolves."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        # give player 1 three 5m tiles + filler for open kan
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="555368", pin="2479", sou="358")
        round_state.current_player_seat = 0

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN)],
        )

        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=tile_id, kan_type=KanType.OPEN)
        )

        # should resolve: open kan executed through resolution
        assert round_state.pending_call_prompt is None
        meld_events = [e for e in result.events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].meld_type == MeldViewType.KAN

    def test_handle_open_kan_four_kans_abort(self):
        """Open kan through resolve_call_prompt triggers four kans abortive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # three players each have one kan meld already
        round_state.players[0].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="2222"),
                opened=True,
                who=0,
                from_who=1,
            )
        ]
        round_state.players[2].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="3333"),
                opened=True,
                who=2,
                from_who=0,
            )
        ]
        round_state.players[3].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="4444"),
                opened=True,
                who=3,
                from_who=0,
            )
        ]

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        # give player 1 three 5m tiles for open kan
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="555368", pin="2479", sou="358")
        round_state.current_player_seat = 0

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN)],
        )

        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=tile_id, kan_type=KanType.OPEN)
        )

        assert round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS

    def test_handle_open_kan_not_pending_caller(self):
        """Open kan from non-pending seat returns error."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        # set up prompt for seat 1, but seat 2 tries open kan
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1},
            callers=[MeldCaller(seat=1, call_type=MeldCallType.PON)],
        )

        result = handle_kan(
            round_state, game_state, seat=2, data=KanActionData(tile_id=tile_id, kan_type=KanType.OPEN)
        )

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_kan"
        assert error_events[0].message == "not a pending caller"

    def test_handle_open_kan_waiting_for_other_callers(self):
        """Open kan with other pending callers returns empty events (waiting)."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats={1, 2},
            callers=[
                MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN),
                MeldCaller(seat=2, call_type=MeldCallType.PON),
            ],
        )

        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=tile_id, kan_type=KanType.OPEN)
        )

        assert result.events == []
        assert round_state.pending_call_prompt is not None
        assert round_state.pending_call_prompt.pending_seats == {2}

    def test_handle_kan_wrong_turn_non_open(self):
        """Non-open kan when not player's turn returns error."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        round_state.current_player_seat = 0

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=tile_id, kan_type=KanType.CLOSED)
        )

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "not_your_turn"

    def test_handle_kan_invalid_closed_kan(self):
        """Closed kan with invalid tiles returns error."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        draw_tile(round_state)
        round_state.current_player_seat = 0

        # player 0 doesn't have 4 copies of this tile
        chun_tile = TilesConverter.string_to_136_array(honors="7")[0]
        result = handle_kan(
            round_state, game_state, seat=0, data=KanActionData(tile_id=chun_tile, kan_type=KanType.CLOSED)
        )

        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == "invalid_kan"
