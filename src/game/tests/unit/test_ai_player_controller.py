"""
Unit tests for AIPlayerController decision-making.

Tests the get_turn_action and get_call_response routing logic
that maps AI player decisions to GameAction + data for dispatch.
"""

from mahjong.tile import TilesConverter

from game.logic.ai_player import AIPlayer, AIPlayerStrategy
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import CallType, GameAction, MeldCallType, RoundPhase
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.types import MeldCaller
from game.logic.wall import Wall
from game.tests.unit.helpers import _string_to_136_tile


class TestAIPlayerControllerGetTurnAction:
    def _create_round_state(self, current_seat: int = 1) -> MahjongRoundState:
        """Create round state for testing."""
        non_winning_hand = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="13579")
        players = (
            MahjongPlayer(seat=0, name="Player", tiles=tuple(non_winning_hand[:13]), score=25000),
            MahjongPlayer(seat=1, name="AI1", tiles=tuple(non_winning_hand), score=25000),
            MahjongPlayer(seat=2, name="AI2", tiles=tuple(non_winning_hand[:13]), score=25000),
            MahjongPlayer(seat=3, name="AI3", tiles=tuple(non_winning_hand[:13]), score=25000),
        )
        return MahjongRoundState(
            players=players,
            wall=Wall(
                live_tiles=tuple(range(50)),
                dead_wall_tiles=tuple(range(14)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
            current_player_seat=current_seat,
            phase=RoundPhase.PLAYING,
        )

    def test_get_turn_action_returns_discard(self):
        """get_turn_action returns discard action for tsumogiri AI player."""
        ai_players = {1: AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)}
        controller = AIPlayerController(ai_players)
        round_state = self._create_round_state(current_seat=1)

        result = controller.get_turn_action(1, round_state)

        assert result is not None
        action, data = result
        assert action == GameAction.DISCARD
        assert "tile_id" in data

    def test_get_turn_action_returns_none_for_non_ai_player(self):
        """get_turn_action returns None for non-AI-player seat."""
        ai_players = {1: AIPlayer()}
        controller = AIPlayerController(ai_players)
        round_state = self._create_round_state(current_seat=0)

        result = controller.get_turn_action(0, round_state)

        assert result is None


class TestAIPlayerControllerGetCallResponse:
    def _create_round_state(self) -> MahjongRoundState:
        """Create round state for testing."""
        players = (
            MahjongPlayer(seat=0, name="Player", tiles=(), score=25000),
            MahjongPlayer(seat=1, name="AI1", tiles=(), score=25000),
            MahjongPlayer(seat=2, name="AI2", tiles=(), score=25000),
            MahjongPlayer(seat=3, name="AI3", tiles=(), score=25000),
        )
        return MahjongRoundState(
            players=players,
            wall=Wall(live_tiles=tuple(range(50))),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )

    def test_get_call_response_returns_none_for_non_ai_player(self):
        """get_call_response returns None for non-AI-player seat."""
        ai_players = {1: AIPlayer(), 2: AIPlayer(), 3: AIPlayer()}
        controller = AIPlayerController(ai_players)
        round_state = self._create_round_state()

        result = controller.get_call_response(0, round_state, CallType.MELD, 0, 0)

        assert result is None

    def test_get_call_response_tsumogiri_declines_ron(self):
        """Tsumogiri AI player declines ron opportunities on DISCARD prompt."""
        ai_players = {1: AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)}
        controller = AIPlayerController(ai_players)
        round_state = self._create_round_state()

        result = controller.get_call_response(1, round_state, CallType.DISCARD, 0, 1)

        assert result is None

    def test_get_call_response_tsumogiri_declines_meld(self):
        """Tsumogiri AI player declines meld opportunities on DISCARD prompt."""
        ai_players = {1: AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)}
        controller = AIPlayerController(ai_players)
        round_state = self._create_round_state()

        caller_info = MeldCaller(
            seat=1,
            call_type=MeldCallType.PON,
        )

        result = controller.get_call_response(
            1, round_state, CallType.DISCARD, _string_to_136_tile(man="1"), caller_info
        )

        assert result is None
