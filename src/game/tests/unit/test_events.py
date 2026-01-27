"""
Tests for game event classes.
"""

from game.messaging.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    ErrorEvent,
    Event,
    MeldEvent,
    PassAcknowledgedEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    TurnEvent,
    event_to_wire,
)


class TestDrawEvent:
    def test_create_draw_event(self) -> None:
        event = DrawEvent(seat=0, tile_id=42, tile="1m", target="seat_0")

        assert event.type == "draw"
        assert event.seat == 0
        assert event.tile_id == 42
        assert event.tile == "1m"
        assert event.target == "seat_0"

    def test_create_draw_event_different_seat(self) -> None:
        event = DrawEvent(seat=3, tile_id=100, tile="9p", target="seat_3")

        assert event.seat == 3
        assert event.target == "seat_3"


class TestDiscardEvent:
    def test_create_discard_event(self) -> None:
        event = DiscardEvent(
            seat=1,
            tile_id=50,
            tile="5s",
            is_tsumogiri=True,
            is_riichi=False,
        )

        assert event.type == "discard"
        assert event.seat == 1
        assert event.tile_id == 50
        assert event.tile == "5s"
        assert event.is_tsumogiri is True
        assert event.is_riichi is False
        assert event.target == "all"

    def test_create_discard_event_with_riichi(self) -> None:
        event = DiscardEvent(
            seat=2,
            tile_id=60,
            tile="E",
            is_tsumogiri=False,
            is_riichi=True,
        )

        assert event.is_riichi is True
        assert event.is_tsumogiri is False


class TestMeldEvent:
    def test_create_pon_event(self) -> None:
        event = MeldEvent(
            meld_type="pon",
            caller_seat=1,
            tile_ids=[10, 11, 12],
            tiles=["3m", "3m", "3m"],
            from_seat=0,
        )

        assert event.type == "meld"
        assert event.meld_type == "pon"
        assert event.caller_seat == 1
        assert event.from_seat == 0
        assert event.tile_ids == [10, 11, 12]
        assert event.tiles == ["3m", "3m", "3m"]
        assert event.kan_type is None
        assert event.target == "all"

    def test_create_chi_event(self) -> None:
        event = MeldEvent(
            meld_type="chi",
            caller_seat=2,
            tile_ids=[0, 4, 8],
            tiles=["1m", "2m", "3m"],
            from_seat=1,
        )

        assert event.meld_type == "chi"
        assert event.from_seat == 1

    def test_create_closed_kan_event(self) -> None:
        event = MeldEvent(
            meld_type="kan",
            caller_seat=0,
            tile_ids=[36, 37, 38, 39],
            tiles=["1p", "1p", "1p", "1p"],
            kan_type="closed",
        )

        assert event.meld_type == "kan"
        assert event.kan_type == "closed"
        assert event.from_seat is None

    def test_create_open_kan_event(self) -> None:
        event = MeldEvent(
            meld_type="kan",
            caller_seat=3,
            tile_ids=[72, 73, 74, 75],
            tiles=["1s", "1s", "1s", "1s"],
            from_seat=2,
            kan_type="open",
        )

        assert event.kan_type == "open"
        assert event.from_seat == 2

    def test_create_added_kan_event(self) -> None:
        event = MeldEvent(
            meld_type="kan",
            caller_seat=1,
            tile_ids=[108, 109, 110, 111],
            tiles=["E", "E", "E", "E"],
            kan_type="added",
        )

        assert event.kan_type == "added"


class TestTurnEvent:
    def test_create_turn_event(self) -> None:
        # available_actions is now a list format
        available_actions = [
            {"action": "discard", "tiles": [10, 20, 30]},
            {"action": "riichi"},
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
        event = CallPromptEvent(
            call_type="ron",
            tile_id=42,
            from_seat=0,
            callers=[1, 2],
            target="all",
        )

        assert event.type == "call_prompt"
        assert event.call_type == "ron"
        assert event.tile_id == 42
        assert event.from_seat == 0
        assert event.callers == [1, 2]
        assert event.target == "all"

    def test_meld_call_prompt(self) -> None:
        callers = [
            {"seat": 1, "call_type": "pon", "tile_34": 5, "priority": 1},
            {"seat": 2, "call_type": "chi", "tile_34": 5, "options": [(4, 8)], "priority": 2},
        ]
        event = CallPromptEvent(
            call_type="meld",
            tile_id=20,
            from_seat=0,
            callers=callers,
            target="all",
        )

        assert event.call_type == "meld"
        assert len(event.callers) == 2

    def test_chankan_call_prompt(self) -> None:
        event = CallPromptEvent(
            call_type="chankan",
            tile_id=50,
            from_seat=2,
            callers=[0, 3],
            target="all",
        )

        assert event.call_type == "chankan"


class TestRoundEndEvent:
    def test_tsumo_round_end(self) -> None:
        result = {
            "type": "tsumo",
            "winner_seat": 0,
            "hand_result": {"han": 3, "fu": 30, "yaku": ["riichi", "tanyao"]},
            "score_changes": {0: 3900, 1: -1300, 2: -1300, 3: -1300},
        }
        event = RoundEndEvent(result=result, target="all")

        assert event.type == "round_end"
        assert event.result == result
        assert event.target == "all"

    def test_ron_round_end(self) -> None:
        result = {
            "type": "ron",
            "winner_seat": 1,
            "loser_seat": 0,
            "hand_result": {"han": 2, "fu": 40, "yaku": ["yakuhai"]},
            "score_changes": {0: -2600, 1: 2600, 2: 0, 3: 0},
        }
        event = RoundEndEvent(result=result, target="all")

        assert event.result["type"] == "ron"

    def test_exhaustive_draw_round_end(self) -> None:
        result = {
            "type": "exhaustive_draw",
            "tempai_seats": [0, 2],
            "noten_seats": [1, 3],
        }
        event = RoundEndEvent(result=result, target="all")

        assert event.result["type"] == "exhaustive_draw"


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


class TestPassAcknowledgedEvent:
    def test_pass_acknowledged_event(self) -> None:
        event = PassAcknowledgedEvent(seat=3, target="seat_3")

        assert event.type == "pass_acknowledged"
        assert event.seat == 3
        assert event.target == "seat_3"


class TestEventToWire:
    def test_draw_event_to_wire(self) -> None:
        event = DrawEvent(seat=0, tile_id=42, tile="1m", target="seat_0")
        wire = event_to_wire(event)

        assert wire == {
            "type": "draw",
            "seat": 0,
            "tile_id": 42,
            "tile": "1m",
            "target": "seat_0",
        }

    def test_discard_event_to_wire(self) -> None:
        event = DiscardEvent(
            seat=1,
            tile_id=50,
            tile="5s",
            is_tsumogiri=True,
            is_riichi=False,
        )
        wire = event_to_wire(event)

        assert wire == {
            "type": "discard",
            "seat": 1,
            "tile_id": 50,
            "tile": "5s",
            "is_tsumogiri": True,
            "is_riichi": False,
            "target": "all",
        }

    def test_meld_event_to_wire(self) -> None:
        event = MeldEvent(
            meld_type="pon",
            caller_seat=1,
            tile_ids=[10, 11, 12],
            tiles=["3m", "3m", "3m"],
            from_seat=0,
        )
        wire = event_to_wire(event)

        assert wire["type"] == "meld"
        assert wire["meld_type"] == "pon"
        assert wire["caller_seat"] == 1
        assert wire["from_seat"] == 0
        assert wire["tile_ids"] == [10, 11, 12]
        assert wire["tiles"] == ["3m", "3m", "3m"]
        assert wire["kan_type"] is None
        assert wire["target"] == "all"

    def test_turn_event_to_wire(self) -> None:
        # available_actions is now a list format
        available_actions = [
            {"action": "discard", "tiles": [10]},
            {"action": "tsumo"},
        ]
        event = TurnEvent(current_seat=0, available_actions=available_actions, wall_count=50, target="seat_0")
        wire = event_to_wire(event)

        assert wire["type"] == "turn"
        assert wire["current_seat"] == 0
        assert wire["available_actions"] == available_actions
        assert wire["wall_count"] == 50

    def test_round_end_event_to_wire(self) -> None:
        result = {"type": "tsumo", "winner_seat": 0}
        event = RoundEndEvent(result=result, target="all")
        wire = event_to_wire(event)

        assert wire["type"] == "round_end"
        assert wire["result"] == result


class TestEventUnionType:
    def test_event_union_type_contains_all_events(self) -> None:
        # verify all event types can be assigned to Event
        events: list[Event] = [
            DrawEvent(seat=0, tile_id=1, tile="1m", target="seat_0"),
            DiscardEvent(seat=0, tile_id=1, tile="1m", is_tsumogiri=False, is_riichi=False),
            MeldEvent(meld_type="pon", caller_seat=0, tile_ids=[1, 2, 3], tiles=["1m", "1m", "1m"]),
            TurnEvent(current_seat=0, available_actions=[], wall_count=70, target="seat_0"),
            CallPromptEvent(call_type="ron", tile_id=1, from_seat=0, callers=[1], target="all"),
            RoundEndEvent(result={}, target="all"),
            RiichiDeclaredEvent(seat=0, target="all"),
            ErrorEvent(code="test", message="test", target="all"),
            PassAcknowledgedEvent(seat=0, target="seat_0"),
        ]

        assert len(events) == 9
