"""
Unit tests for BotController.
"""

from mahjong.tile import TilesConverter

from game.logic.bot import BotPlayer, BotStrategy
from game.logic.bot_controller import BotController
from game.logic.enums import CallType, GameAction, MeldCallType, RoundPhase, RoundResultType
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.types import HandResultInfo, MeldCaller, TsumoResult
from game.messaging.events import (
    DrawEvent,
    EventType,
    RoundEndEvent,
    ServiceEvent,
    convert_events,
    extract_round_result,
)
from game.tests.unit.helpers import _string_to_136_tile


class TestBotControllerInit:
    def test_init_with_bots(self):
        """BotController initializes with dict of bots."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller._bots == bots

    def test_init_with_empty_dict(self):
        """BotController can be initialized with empty dict."""
        controller = BotController({})

        assert controller._bots == {}


class TestBotControllerGetBot:
    def test_get_bot_for_valid_seat(self):
        """_get_bot returns correct bot for valid seat."""
        bot1, bot2, bot3 = BotPlayer(), BotPlayer(), BotPlayer()
        bots = {1: bot1, 2: bot2, 3: bot3}
        controller = BotController(bots)

        assert controller._get_bot(1) is bot1
        assert controller._get_bot(2) is bot2
        assert controller._get_bot(3) is bot3

    def test_get_bot_for_non_bot_seat(self):
        """_get_bot returns None for seat without a bot."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller._get_bot(0) is None

    def test_get_bot_for_invalid_seat(self):
        """_get_bot returns None for invalid seat."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller._get_bot(4) is None
        assert controller._get_bot(-1) is None


class TestBotControllerIsBot:
    def test_is_bot_returns_true_for_bot_seat(self):
        """is_bot returns True for seats with bots."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller.is_bot(1) is True
        assert controller.is_bot(2) is True
        assert controller.is_bot(3) is True

    def test_is_bot_returns_false_for_non_bot_seat(self):
        """is_bot returns False for seats without bots."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller.is_bot(0) is False

    def test_is_bot_returns_false_for_invalid_seat(self):
        """is_bot returns False for invalid seats."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller.is_bot(4) is False
        assert controller.is_bot(-1) is False


class TestBotControllerBotSeats:
    def test_bot_seats_returns_set_of_bot_seats(self):
        """bot_seats returns the correct set of seats."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)

        assert controller.bot_seats == {1, 2, 3}

    def test_bot_seats_empty_when_no_bots(self):
        """bot_seats returns empty set when no bots."""
        controller = BotController({})

        assert controller.bot_seats == set()


class TestBotControllerAddBot:
    def test_add_bot_registers_bot_at_seat(self):
        """add_bot registers a new bot at the given seat."""
        controller = BotController({})
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)

        controller.add_bot(2, bot)

        assert controller.is_bot(2) is True
        assert controller._get_bot(2) is bot

    def test_add_bot_to_existing_controller(self):
        """add_bot adds a bot alongside existing bots."""
        bots = {1: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        new_bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)

        controller.add_bot(0, new_bot)

        assert controller.is_bot(0) is True
        assert controller.is_bot(1) is True
        assert controller.is_bot(3) is True
        assert controller.bot_seats == {0, 1, 3}

    def test_add_bot_overwrites_existing_bot(self):
        """add_bot replaces an existing bot at the same seat."""
        old_bot = BotPlayer()
        controller = BotController({2: old_bot})
        new_bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)

        controller.add_bot(2, new_bot)

        assert controller._get_bot(2) is new_bot
        assert controller._get_bot(2) is not old_bot


class TestBotControllerGetTurnAction:
    def _create_round_state(self, current_seat: int = 1) -> MahjongRoundState:
        """Create round state for testing."""
        non_winning_hand = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="13579")
        players = (
            MahjongPlayer(seat=0, name="Human", tiles=tuple(non_winning_hand[:13])),
            MahjongPlayer(seat=1, name="Bot1", tiles=tuple(non_winning_hand)),
            MahjongPlayer(seat=2, name="Bot2", tiles=tuple(non_winning_hand[:13])),
            MahjongPlayer(seat=3, name="Bot3", tiles=tuple(non_winning_hand[:13])),
        )
        return MahjongRoundState(
            players=players,
            wall=tuple(range(50)),
            dead_wall=tuple(range(14)),
            dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            current_player_seat=current_seat,
            phase=RoundPhase.PLAYING,
        )

    def test_get_turn_action_returns_discard(self):
        """get_turn_action returns discard action for tsumogiri bot."""
        bots = {1: BotPlayer(strategy=BotStrategy.TSUMOGIRI)}
        controller = BotController(bots)
        round_state = self._create_round_state(current_seat=1)

        result = controller.get_turn_action(1, round_state)

        assert result is not None
        action, data = result
        assert action == GameAction.DISCARD
        assert "tile_id" in data

    def test_get_turn_action_returns_none_for_non_bot(self):
        """get_turn_action returns None for non-bot seat."""
        bots = {1: BotPlayer()}
        controller = BotController(bots)
        round_state = self._create_round_state(current_seat=0)

        result = controller.get_turn_action(0, round_state)

        assert result is None


class TestBotControllerGetCallResponse:
    def _create_round_state(self) -> MahjongRoundState:
        """Create round state for testing."""
        players = (
            MahjongPlayer(seat=0, name="Human", tiles=()),
            MahjongPlayer(seat=1, name="Bot1", tiles=()),
            MahjongPlayer(seat=2, name="Bot2", tiles=()),
            MahjongPlayer(seat=3, name="Bot3", tiles=()),
        )
        return MahjongRoundState(
            players=players,
            wall=tuple(range(50)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )

    def test_get_call_response_returns_none_for_non_bot(self):
        """get_call_response returns None for non-bot seat."""
        bots = {1: BotPlayer(), 2: BotPlayer(), 3: BotPlayer()}
        controller = BotController(bots)
        round_state = self._create_round_state()

        result = controller.get_call_response(0, round_state, CallType.MELD, 0, 0)

        assert result is None

    def test_get_call_response_tsumogiri_declines_ron(self):
        """Tsumogiri bot declines ron opportunities."""
        bots = {1: BotPlayer(strategy=BotStrategy.TSUMOGIRI)}
        controller = BotController(bots)
        round_state = self._create_round_state()

        result = controller.get_call_response(1, round_state, CallType.RON, 0, 1)

        assert result is None

    def test_get_call_response_tsumogiri_declines_meld(self):
        """Tsumogiri bot declines meld opportunities."""
        bots = {1: BotPlayer(strategy=BotStrategy.TSUMOGIRI)}
        controller = BotController(bots)
        round_state = self._create_round_state()

        caller_info = MeldCaller(
            seat=1,
            call_type=MeldCallType.PON,
        )

        result = controller.get_call_response(
            1, round_state, CallType.MELD, _string_to_136_tile(man="1"), caller_info
        )

        assert result is None


class TestConvertEvents:
    def test_convert_events_handles_typed_events(self):
        """convert_events converts typed events to ServiceEvent format."""
        events = [DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0")]

        result = convert_events(events)

        assert len(result) == 1
        assert isinstance(result[0], ServiceEvent)
        assert result[0].event == EventType.DRAW
        assert isinstance(result[0].data, DrawEvent)
        assert result[0].data.seat == 0
        assert result[0].target == "seat_0"


class TestExtractRoundResult:
    def test_extract_round_result_finds_result(self):
        """extract_round_result extracts result from round_end event."""
        tsumo_result = TsumoResult(
            winner_seat=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["tanyao"]),
            score_changes={0: 1000},
            riichi_sticks_collected=0,
        )
        events = [
            ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0"),
            ),
            ServiceEvent(event=EventType.ROUND_END, data=RoundEndEvent(result=tsumo_result, target="all")),
        ]

        result = extract_round_result(events)

        assert result is not None
        assert isinstance(result, TsumoResult)
        assert result.type == RoundResultType.TSUMO
        assert result.winner_seat == 0

    def test_extract_round_result_no_round_end(self):
        """extract_round_result returns None when no round_end event."""
        events = [
            ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0"),
            ),
            ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0"),
            ),
        ]

        result = extract_round_result(events)

        assert result is None
