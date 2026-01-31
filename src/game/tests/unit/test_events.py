"""
Tests for game event classes.
"""

from mahjong.tile import TilesConverter

from game.logic.enums import AbortiveDrawType, KanType, MeldCallType, MeldViewType, PlayerAction
from game.logic.types import (
    AbortiveDrawResult,
    AvailableActionItem,
    ExhaustiveDrawResult,
    GameEndResult,
    GamePlayerInfo,
    GameView,
    HandResultInfo,
    MeldCaller,
    PlayerStanding,
    PlayerView,
    RonResult,
    TsumoResult,
)
from game.messaging.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    ErrorEvent,
    Event,
    GameEndedEvent,
    GameStartedEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    RoundStartedEvent,
    TurnEvent,
)


class TestDrawEvent:
    def test_create_draw_event(self) -> None:
        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        event = DrawEvent(seat=0, tile_id=tile_id, target="seat_0")

        assert event.type == "draw"
        assert event.seat == 0
        assert event.tile_id == tile_id
        assert event.target == "seat_0"

    def test_create_draw_event_different_seat(self) -> None:
        tile_id = TilesConverter.string_to_136_array(pin="9")[0]
        event = DrawEvent(seat=3, tile_id=tile_id, target="seat_3")

        assert event.seat == 3
        assert event.target == "seat_3"


class TestDiscardEvent:
    def test_create_discard_event(self) -> None:
        tile_id = TilesConverter.string_to_136_array(sou="5")[0]
        event = DiscardEvent(
            seat=1,
            tile_id=tile_id,
            is_tsumogiri=True,
            is_riichi=False,
        )

        assert event.type == "discard"
        assert event.seat == 1
        assert event.tile_id == tile_id
        assert event.is_tsumogiri is True
        assert event.is_riichi is False
        assert event.target == "all"

    def test_create_discard_event_with_riichi(self) -> None:
        tile_id = TilesConverter.string_to_136_array(honors="1")[0]
        event = DiscardEvent(
            seat=2,
            tile_id=tile_id,
            is_tsumogiri=False,
            is_riichi=True,
        )

        assert event.is_riichi is True
        assert event.is_tsumogiri is False


class TestMeldEvent:
    def test_create_pon_event(self) -> None:
        pon_tile_ids = TilesConverter.string_to_136_array(man="333")
        event = MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=1,
            tile_ids=pon_tile_ids,
            from_seat=0,
        )

        assert event.type == "meld"
        assert event.meld_type == MeldViewType.PON
        assert event.caller_seat == 1
        assert event.from_seat == 0
        assert event.tile_ids == pon_tile_ids
        assert event.kan_type is None
        assert event.target == "all"

    def test_create_chi_event(self) -> None:
        event = MeldEvent(
            meld_type=MeldViewType.CHI,
            caller_seat=2,
            tile_ids=TilesConverter.string_to_136_array(man="123"),
            from_seat=1,
        )

        assert event.meld_type == MeldViewType.CHI
        assert event.from_seat == 1

    def test_create_closed_kan_event(self) -> None:
        event = MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=0,
            tile_ids=TilesConverter.string_to_136_array(pin="1111"),
            kan_type=KanType.CLOSED,
        )

        assert event.meld_type == MeldViewType.KAN
        assert event.kan_type == KanType.CLOSED
        assert event.from_seat is None

    def test_create_open_kan_event(self) -> None:
        event = MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=3,
            tile_ids=TilesConverter.string_to_136_array(sou="1111"),
            from_seat=2,
            kan_type=KanType.OPEN,
        )

        assert event.kan_type == KanType.OPEN
        assert event.from_seat == 2

    def test_create_added_kan_event(self) -> None:
        event = MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=1,
            tile_ids=TilesConverter.string_to_136_array(honors="1111"),
            kan_type=KanType.ADDED,
        )

        assert event.kan_type == KanType.ADDED


class TestTurnEvent:
    def test_create_turn_event(self) -> None:
        discard_tiles = TilesConverter.string_to_136_array(man="368")
        available_actions = [
            AvailableActionItem(action=PlayerAction.DISCARD, tiles=discard_tiles),
            AvailableActionItem(action=PlayerAction.RIICHI),
        ]
        event = TurnEvent(
            current_seat=2,
            available_actions=available_actions,
            wall_count=70,
            target="seat_2",
        )

        assert event.type == "turn"
        assert event.current_seat == 2
        assert event.available_actions == available_actions
        assert event.wall_count == 70
        assert event.target == "seat_2"


class TestCallPromptEvent:
    def test_ron_call_prompt(self) -> None:
        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        event = CallPromptEvent(
            call_type="ron",
            tile_id=tile_id,
            from_seat=0,
            callers=[1, 2],
            target="all",
        )

        assert event.type == "call_prompt"
        assert event.call_type == "ron"
        assert event.tile_id == tile_id
        assert event.from_seat == 0
        assert event.callers == [1, 2]
        assert event.target == "all"

    def test_meld_call_prompt(self) -> None:
        callers = [
            MeldCaller(seat=1, call_type=MeldCallType.PON),
            MeldCaller(seat=2, call_type=MeldCallType.CHI, options=[(4, 8)]),
        ]
        event = CallPromptEvent(
            call_type="meld",
            tile_id=TilesConverter.string_to_136_array(man="6")[0],
            from_seat=0,
            callers=callers,
            target="all",
        )

        assert event.call_type == "meld"
        assert len(event.callers) == 2

    def test_chankan_call_prompt(self) -> None:
        event = CallPromptEvent(
            call_type="chankan",
            tile_id=TilesConverter.string_to_136_array(pin="4")[0],
            from_seat=2,
            callers=[0, 3],
            target="all",
        )

        assert event.call_type == "chankan"


class TestRoundEndEvent:
    def test_tsumo_round_end(self) -> None:
        result = TsumoResult(
            winner_seat=0,
            hand_result=HandResultInfo(han=3, fu=30, yaku=["riichi", "tanyao"]),
            score_changes={0: 3900, 1: -1300, 2: -1300, 3: -1300},
            riichi_sticks_collected=0,
        )
        event = RoundEndEvent(result=result, target="all")

        assert event.type == "round_end"
        assert event.result == result
        assert event.target == "all"

    def test_ron_round_end(self) -> None:
        result = RonResult(
            winner_seat=1,
            loser_seat=0,
            hand_result=HandResultInfo(han=2, fu=40, yaku=["yakuhai"]),
            score_changes={0: -2600, 1: 2600, 2: 0, 3: 0},
            riichi_sticks_collected=0,
        )
        event = RoundEndEvent(result=result, target="all")

        assert event.result.type == "ron"

    def test_exhaustive_draw_round_end(self) -> None:
        result = ExhaustiveDrawResult(
            tempai_seats=[0, 2],
            noten_seats=[1, 3],
            score_changes={},
        )
        event = RoundEndEvent(result=result, target="all")

        assert event.result.type == "exhaustive_draw"


class TestRiichiDeclaredEvent:
    def test_riichi_declared_event(self) -> None:
        event = RiichiDeclaredEvent(seat=1, target="all")

        assert event.type == "riichi_declared"
        assert event.seat == 1
        assert event.target == "all"


class TestErrorEvent:
    def test_create_error_event(self) -> None:
        event = ErrorEvent(
            code="invalid_action",
            message="Cannot discard that tile",
            target="all",
        )

        assert event.type == "error"
        assert event.code == "invalid_action"
        assert event.message == "Cannot discard that tile"
        assert event.target == "all"

    def test_create_error_event_with_target(self) -> None:
        event = ErrorEvent(
            code="not_your_turn",
            message="Wait for your turn",
            target="seat_2",
        )

        assert event.target == "seat_2"


class TestEventModelDump:
    """Test that events serialize correctly for wire format."""

    def test_draw_event_to_wire(self) -> None:
        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        event = DrawEvent(seat=0, tile_id=tile_id, target="seat_0")
        wire = event.model_dump()

        assert wire == {
            "type": "draw",
            "seat": 0,
            "tile_id": tile_id,
            "target": "seat_0",
        }

    def test_discard_event_to_wire(self) -> None:
        tile_id = TilesConverter.string_to_136_array(sou="5")[0]
        event = DiscardEvent(
            seat=1,
            tile_id=tile_id,
            is_tsumogiri=True,
            is_riichi=False,
        )
        wire = event.model_dump()

        assert wire == {
            "type": "discard",
            "seat": 1,
            "tile_id": tile_id,
            "is_tsumogiri": True,
            "is_riichi": False,
            "target": "all",
        }

    def test_meld_event_to_wire(self) -> None:
        pon_tile_ids = TilesConverter.string_to_136_array(man="333")
        event = MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=1,
            tile_ids=pon_tile_ids,
            from_seat=0,
        )
        wire = event.model_dump()

        assert wire["type"] == "meld"
        assert wire["meld_type"] == "pon"
        assert wire["caller_seat"] == 1
        assert wire["from_seat"] == 0
        assert wire["tile_ids"] == pon_tile_ids
        assert wire["kan_type"] is None
        assert wire["target"] == "all"

    def test_turn_event_to_wire(self) -> None:
        discard_tiles = TilesConverter.string_to_136_array(man="3")
        available_actions = [
            AvailableActionItem(action=PlayerAction.DISCARD, tiles=discard_tiles),
            AvailableActionItem(action=PlayerAction.TSUMO),
        ]
        event = TurnEvent(current_seat=0, available_actions=available_actions, wall_count=50, target="seat_0")
        wire = event.model_dump()

        assert wire["type"] == "turn"
        assert wire["current_seat"] == 0
        assert wire["available_actions"][0]["action"] == "discard"
        assert wire["available_actions"][0]["tiles"] == discard_tiles
        assert wire["wall_count"] == 50

    def test_round_end_event_to_wire(self) -> None:
        result = TsumoResult(
            winner_seat=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["tanyao"]),
            score_changes={0: 1000},
            riichi_sticks_collected=0,
        )
        event = RoundEndEvent(result=result, target="all")
        wire = event.model_dump()

        assert wire["type"] == "round_end"
        assert wire["result"]["type"] == "tsumo"
        assert wire["result"]["winner_seat"] == 0


class TestEventUnionType:
    def test_event_union_type_contains_all_events(self) -> None:
        # verify all event types can be assigned to Event
        mock_view = GameView(
            seat=0,
            round_wind="East",
            round_number=1,
            dealer_seat=0,
            current_player_seat=0,
            wall_count=70,
            dora_indicators=[],
            honba_sticks=0,
            riichi_sticks=0,
            players=[
                PlayerView(
                    seat=i,
                    name=f"Player{i}",
                    is_bot=i > 0,
                    score=25000,
                    is_riichi=False,
                    discards=[],
                    melds=[],
                    tile_count=13,
                )
                for i in range(4)
            ],
            phase="playing",
            game_phase="east",
        )
        man_1_tile_id = TilesConverter.string_to_136_array(man="1")[0]
        man_1_pon_ids = TilesConverter.string_to_136_array(man="111")
        events: list[Event] = [
            DrawEvent(seat=0, tile_id=man_1_tile_id, target="seat_0"),
            DiscardEvent(seat=0, tile_id=man_1_tile_id, is_tsumogiri=False, is_riichi=False),
            MeldEvent(meld_type=MeldViewType.PON, caller_seat=0, tile_ids=man_1_pon_ids),
            TurnEvent(current_seat=0, available_actions=[], wall_count=70, target="seat_0"),
            CallPromptEvent(call_type="ron", tile_id=man_1_tile_id, from_seat=0, callers=[1], target="all"),
            RoundEndEvent(result=AbortiveDrawResult(reason=AbortiveDrawType.NINE_TERMINALS), target="all"),
            RiichiDeclaredEvent(seat=0, target="all"),
            ErrorEvent(code="test", message="test", target="all"),
            GameStartedEvent(
                players=[GamePlayerInfo(seat=i, name=f"Player{i}", is_bot=i > 0) for i in range(4)],
            ),
            RoundStartedEvent(view=mock_view, target="seat_0"),
            GameEndedEvent(
                result=GameEndResult(
                    winner_seat=0,
                    standings=[
                        PlayerStanding(seat=0, name="Player0", score=30000, final_score=40, is_bot=False),
                    ],
                ),
                target="all",
            ),
        ]

        assert len(events) == 11
