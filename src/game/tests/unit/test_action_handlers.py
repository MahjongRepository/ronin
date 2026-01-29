"""
Unit tests for action handlers.
"""

from game.logic.action_handlers import (
    ActionResult,
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
from game.logic.enums import AbortiveDrawType, BotType, KanType, MeldViewType
from game.logic.game import init_game
from game.logic.round import discard_tile, draw_tile
from game.logic.state import MahjongGameState, RoundPhase
from game.logic.types import (
    AbortiveDrawResult,
    ChiActionData,
    DiscardActionData,
    KanActionData,
    PonActionData,
    RiichiActionData,
    RonActionData,
    SeatConfig,
)
from game.messaging.events import (
    DiscardEvent,
    ErrorEvent,
    MeldEvent,
    PassAcknowledgedEvent,
    RoundEndEvent,
    TurnEvent,
)


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player", is_bot=False),
        SeatConfig(name="Tsumogiri 1", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", is_bot=True, bot_type=BotType.TSUMOGIRI),
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

        result = handle_discard(round_state, game_state, seat=1, data=DiscardActionData(tile_id=0))

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
        round_state.players[0].tiles = [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,
            38,  # 111p
            44,  # 3p (will discard this)
        ]
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

        result = handle_riichi(round_state, game_state, seat=1, data=RiichiActionData(tile_id=0))

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
        round_state.players[0].tiles = [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,
            38,  # 111p
            40,
            41,  # 22p
        ]
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

        # give player 1 a waiting hand
        round_state.players[1].tiles = [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,
            38,  # 111p
            40,  # 2p
        ]

        win_tile = 41  # 2p
        round_state.players[0].tiles.append(win_tile)
        round_state.current_player_seat = 0

        return game_state, win_tile, 0

    def test_handle_ron_success(self):
        game_state, win_tile, discarder_seat = self._create_ron_opportunity()
        round_state = game_state.round_state

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

        # give player 1 two 1m tiles
        round_state.players[1].tiles = [0, 1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]

        tile_to_pon = 2
        round_state.players[0].tiles.append(tile_to_pon)
        round_state.current_player_seat = 0

        return game_state, tile_to_pon

    def test_handle_pon_success(self):
        game_state, tile_to_pon = self._create_pon_opportunity()
        round_state = game_state.round_state

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

        # player 1 has 2m and 3m tiles
        round_state.players[1].tiles = [4, 8, 20, 24, 28, 32, 40, 44, 48, 52, 60, 64, 68]

        # player 0 discards 1m
        round_state.current_player_seat = 0
        tile_to_chi = 0

        return game_state, tile_to_chi, [4, 8]

    def test_handle_chi_success(self):
        game_state, tile_to_chi, sequence_tiles = self._create_chi_opportunity()
        round_state = game_state.round_state

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

        # give player 0 four 1m tiles
        round_state.players[0].tiles = [0, 1, 2, 3, 10, 20, 30, 40, 50, 60, 70, 80, 90]
        draw_tile(round_state)

        return game_state, 0

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
        # terminals: 1m(0-3), 9m(32-35), 1p(36-39), 9p(68-71), 1s(72-75), 9s(104-107)
        # honors: E(108-111), S(112-115), W(116-119), N(120-123), White(124-127), Green(128-131), Red(132-135)
        round_state.players[0].tiles = [
            0,  # 1m
            32,  # 9m
            36,  # 1p
            68,  # 9p
            72,  # 1s
            104,  # 9s
            108,  # E
            112,  # S
            116,  # W
            4,  # 2m (non-terminal for filler)
            8,  # 3m (non-terminal for filler)
            12,  # 4m (non-terminal for filler)
            16,  # 5m (non-terminal for filler)
        ]

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

    def test_handle_pass_acknowledges(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        draw_tile(round_state)

        result = handle_pass(round_state, game_state, seat=0)

        assert isinstance(result, ActionResult)
        pass_events = [e for e in result.events if isinstance(e, PassAcknowledgedEvent)]
        assert len(pass_events) == 1
        assert pass_events[0].seat == 0

    def test_handle_pass_after_discard_advances_turn(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        draw_tile(round_state)

        # simulate a discard leaving current player with 13 tiles
        tile_to_discard = round_state.players[0].tiles[0]
        discard_tile(round_state, 0, tile_to_discard)

        initial_seat = round_state.current_player_seat
        handle_pass(round_state, game_state, seat=1)

        # turn should advance after pass
        assert round_state.current_player_seat == (initial_seat + 1) % 4


class TestActionResult:
    def test_action_result_default_needs_post_discard(self):
        result = ActionResult([])
        assert result.needs_post_discard is False

    def test_action_result_with_needs_post_discard(self):
        result = ActionResult([], needs_post_discard=True)
        assert result.needs_post_discard is True
