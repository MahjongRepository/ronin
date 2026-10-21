from __future__ import annotations

from mahjong.tile import TilesConverter

from game.logic.ai_player import AIPlayer, AIPlayerStrategy
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import CallType, GameAction, KanType, MeldCallType, PlayerAction, RoundPhase
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.tiles import tile_to_34
from game.logic.types import AIPlayerAction, MeldCaller
from game.logic.wall import Wall
from game.tests.unit.helpers import _string_to_136_tile


class _AcceptAllAI(AIPlayer):
    def __init__(self) -> None:
        super().__init__()
        self.last_kan_tile_34: int | None = None

    def should_call_pon(self, player, discarded_tile, round_state) -> bool:
        return True

    def should_call_chi(self, player, discarded_tile, chi_options, round_state):
        if chi_options:
            return chi_options[0]

        return None

    def should_call_kan(self, player, kan_type, tile_34, round_state) -> bool:
        self.last_kan_tile_34 = tile_34
        return True

    def should_call_ron(self, player, discarded_tile, round_state) -> bool:
        return True


def _create_round_state(current_seat: int = 0) -> MahjongRoundState:
    hand = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="13579")
    players = (
        MahjongPlayer(seat=0, name="P0", tiles=tuple(hand[:13]), score=25000),
        MahjongPlayer(seat=1, name="AI1", tiles=tuple(hand), score=25000),
        MahjongPlayer(seat=2, name="P2", tiles=tuple(hand[:13]), score=25000),
        MahjongPlayer(seat=3, name="P3", tiles=tuple(hand[:13]), score=25000),
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


class TestGetTurnAction:
    def test_get_turn_action__when_ai_seat__should_return_discard(self):
        controller = AIPlayerController({1: AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)})
        rs = _create_round_state(current_seat=1)
        expected_tile = rs.players[1].tiles[-1]

        result = controller.get_turn_action(1, rs)
        assert result is not None
        action, data = result
        assert action == GameAction.DISCARD
        assert data["tile_id"] == expected_tile

    def test_get_turn_action__when_non_ai_seat__should_return_none(self):
        controller = AIPlayerController({1: AIPlayer()})
        rs = _create_round_state(current_seat=0)

        assert controller.get_turn_action(0, rs) is None

    def test_get_turn_action__when_ai_tsumos__should_route_to_declare_tsumo(self):
        class TsumoAI(AIPlayer):
            def get_action(self, player, round_state):
                return AIPlayerAction(action=PlayerAction.TSUMO)

        controller = AIPlayerController({1: TsumoAI()})
        rs = _create_round_state(current_seat=1)

        assert controller.get_turn_action(1, rs) == (GameAction.DECLARE_TSUMO, {})

    def test_get_turn_action__when_ai_riichis__should_route_to_declare_riichi_with_tile(self):
        class RiichiAI(AIPlayer):
            def get_action(self, player, round_state):
                return AIPlayerAction(action=PlayerAction.RIICHI, tile_id=42)

        controller = AIPlayerController({1: RiichiAI()})
        rs = _create_round_state(current_seat=1)

        assert controller.get_turn_action(1, rs) == (GameAction.DECLARE_RIICHI, {"tile_id": 42})

    def test_get_turn_action__when_ai_action_unhandled__should_return_none(self):
        class KyuushuAI(AIPlayer):
            def get_action(self, player, round_state):
                return AIPlayerAction(action=PlayerAction.KYUUSHU)

        controller = AIPlayerController({1: KyuushuAI()})
        rs = _create_round_state(current_seat=1)

        assert controller.get_turn_action(1, rs) is None


class TestGetCallResponseTsumogiriDeclines:
    def test_get_call_response__when_tsumogiri_ai_offered_ron__should_decline(self):
        controller = AIPlayerController({1: AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)})
        rs = _create_round_state()

        assert (
            controller.get_call_response(seat=1, round_state=rs, call_type=CallType.RON, tile_id=0, caller_info=1)
            is None
        )

    def test_get_call_response__when_tsumogiri_ai_offered_pon__should_decline(self):
        controller = AIPlayerController({1: AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)})
        rs = _create_round_state()
        caller = MeldCaller(seat=1, call_type=MeldCallType.PON)

        assert (
            controller.get_call_response(
                seat=1,
                round_state=rs,
                call_type=CallType.MELD,
                tile_id=_string_to_136_tile(man="1"),
                caller_info=caller,
            )
            is None
        )

    def test_get_call_response__when_non_ai_seat__should_return_none(self):
        controller = AIPlayerController({1: AIPlayer()})
        rs = _create_round_state()

        assert (
            controller.get_call_response(seat=0, round_state=rs, call_type=CallType.MELD, tile_id=0, caller_info=0)
            is None
        )


class TestGetCallResponseAcceptingAI:
    def test_get_call_response__when_accepting_ai_and_ron_prompt__should_call_ron(self):
        ai = _AcceptAllAI()
        controller = AIPlayerController({1: ai})
        rs = _create_round_state()

        result = controller.get_call_response(seat=1, round_state=rs, call_type=CallType.RON, tile_id=0, caller_info=1)
        assert result is not None
        action, data = result
        assert action == GameAction.CALL_RON
        assert data == {}

    def test_get_call_response__when_accepting_ai_and_chankan_prompt__should_call_ron(self):
        ai = _AcceptAllAI()
        controller = AIPlayerController({1: ai})
        rs = _create_round_state()

        result = controller.get_call_response(
            seat=1, round_state=rs, call_type=CallType.CHANKAN, tile_id=0, caller_info=1
        )
        assert result is not None
        assert result[0] == GameAction.CALL_RON

    def test_get_call_response__when_accepting_ai_and_discard_prompt_int_caller__should_call_ron(self):
        ai = _AcceptAllAI()
        controller = AIPlayerController({1: ai})
        rs = _create_round_state()

        result = controller.get_call_response(
            seat=1, round_state=rs, call_type=CallType.DISCARD, tile_id=0, caller_info=1
        )
        assert result is not None
        assert result[0] == GameAction.CALL_RON

    def test_get_call_response__when_accepting_ai_and_pon__should_call_pon_with_tile_id(self):
        ai = _AcceptAllAI()
        controller = AIPlayerController({1: ai})
        rs = _create_round_state()
        tile_id = _string_to_136_tile(man="1")
        caller = MeldCaller(seat=1, call_type=MeldCallType.PON)

        result = controller.get_call_response(
            seat=1, round_state=rs, call_type=CallType.MELD, tile_id=tile_id, caller_info=caller
        )
        assert result is not None
        action, data = result
        assert action == GameAction.CALL_PON
        assert data == {"tile_id": tile_id}

    def test_get_call_response__when_accepting_ai_and_chi__should_call_chi_with_sequence(self):
        ai = _AcceptAllAI()
        controller = AIPlayerController({1: ai})
        rs = _create_round_state()
        tile_id = _string_to_136_tile(man="3")
        caller = MeldCaller(seat=1, call_type=MeldCallType.CHI, options=((0, 4),))

        result = controller.get_call_response(
            seat=1, round_state=rs, call_type=CallType.MELD, tile_id=tile_id, caller_info=caller
        )
        assert result is not None
        action, data = result
        assert action == GameAction.CALL_CHI
        assert data == {"tile_id": tile_id, "sequence_tiles": (0, 4)}

    def test_get_call_response__when_accepting_ai_and_open_kan__should_call_kan_and_convert_tile_to_34(self):
        ai = _AcceptAllAI()
        controller = AIPlayerController({1: ai})
        rs = _create_round_state()
        tile_id = 40  # 2p copy 0, tile_34=10
        caller = MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN)

        result = controller.get_call_response(
            seat=1, round_state=rs, call_type=CallType.MELD, tile_id=tile_id, caller_info=caller
        )
        assert result is not None
        action, data = result
        assert action == GameAction.CALL_KAN
        assert data == {"tile_id": tile_id, "kan_type": KanType.OPEN}
        assert ai.last_kan_tile_34 == tile_to_34(tile_id)

    def test_get_call_response__when_meld_prompt_with_int_caller__should_return_none(self):
        ai = _AcceptAllAI()
        controller = AIPlayerController({1: ai})
        rs = _create_round_state()

        assert (
            controller.get_call_response(seat=1, round_state=rs, call_type=CallType.MELD, tile_id=0, caller_info=1)
            is None
        )


class TestAIPlayerControllerManagement:
    def test_ai_player_controller__when_ai_player_added__should_mark_seat_as_ai(self):
        controller = AIPlayerController({})
        assert controller.is_ai_player(2) is False

        controller.add_ai_player(2, AIPlayer())
        assert controller.is_ai_player(2) is True

    def test_ai_player_controller__when_ai_player_removed__should_unmark_seat(self):
        ai = AIPlayer()
        controller = AIPlayerController({1: ai})
        assert controller.is_ai_player(1) is True

        controller.remove_ai_player(1)
        assert controller.is_ai_player(1) is False
        assert 1 not in controller.ai_player_seats
