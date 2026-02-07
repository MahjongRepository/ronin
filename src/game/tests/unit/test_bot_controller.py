"""
Unit tests for BotController decision-making.

Tests the get_turn_action and get_call_response routing logic
that maps bot decisions to GameAction + data for dispatch.
"""

from mahjong.tile import TilesConverter

from game.logic.bot import BotPlayer, BotStrategy
from game.logic.bot_controller import BotController
from game.logic.enums import CallType, GameAction, MeldCallType, RoundPhase
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.types import MeldCaller
from game.tests.unit.helpers import _string_to_136_tile


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
