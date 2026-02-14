from game.logic.events import (
    BroadcastTarget,
    DiscardEvent,
    DrawEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.messaging.event_payload import (
    service_event_payload,
    shape_call_prompt_payload,
)


class TestServiceEventPayload:
    """Tests for centralized event payload shaping."""

    def test_broadcast_event_payload(self):
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_tsumogiri=False, is_riichi=True),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert payload["type"] == EventType.DISCARD
        assert payload["seat"] == 0
        assert payload["tile_id"] == 10
        assert payload["is_tsumogiri"] is False
        assert payload["is_riichi"] is True
        # internal fields excluded
        assert "target" not in payload or payload.get("target") is None

    def test_seat_target_event_payload(self):
        event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(seat=1, tile_id=42, target="seat_1"),
            target=SeatTarget(seat=1),
        )
        payload = service_event_payload(event)

        assert payload["type"] == EventType.DRAW
        assert payload["seat"] == 1
        assert payload["tile_id"] == 42

    def test_payload_excludes_type_and_target_fields(self):
        """The 'type' and 'target' from the domain model are excluded from the dump."""
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_tsumogiri=False, is_riichi=False),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        # "type" key exists because we explicitly set it from event.event
        assert "type" in payload
        # but the domain model's "target" string field is excluded
        dumped_keys = set(event.data.model_dump(exclude={"type", "target"}).keys())
        payload_keys = set(payload.keys()) - {"type"}
        assert payload_keys == dumped_keys


class TestShapeCallPromptPayload:
    """Tests for call prompt wire payload shaping."""

    def test_ron_prompt_drops_callers_keeps_caller_seat(self):
        payload = {
            "type": "call_prompt",
            "call_type": "ron",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [0],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result == {
            "type": "call_prompt",
            "call_type": "ron",
            "tile_id": 42,
            "from_seat": 1,
            "caller_seat": 0,
        }

    def test_chankan_prompt_drops_callers_keeps_caller_seat(self):
        payload = {
            "type": "call_prompt",
            "call_type": "chankan",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [3],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result["caller_seat"] == 3

    def test_meld_prompt_replaces_callers_with_available_calls(self):
        payload = {
            "type": "call_prompt",
            "call_type": "meld",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [
                {"seat": 0, "call_type": "pon", "options": None},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result["caller_seat"] == 0
        assert result["available_calls"] == [{"call_type": "pon"}]

    def test_meld_prompt_preserves_chi_options(self):
        payload = {
            "type": "call_prompt",
            "call_type": "meld",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [
                {"seat": 0, "call_type": "chi", "options": [[40, 44]]},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert result["caller_seat"] == 0
        assert result["available_calls"] == [
            {"call_type": "chi", "options": [[40, 44]]},
        ]

    def test_unknown_call_type_returns_payload_unchanged(self):
        payload = {
            "type": "call_prompt",
            "call_type": "unknown",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [0],
        }
        result = shape_call_prompt_payload(payload)

        assert result == payload
        assert result["callers"] == [0]

    def test_meld_prompt_multiple_call_types(self):
        payload = {
            "type": "call_prompt",
            "call_type": "meld",
            "tile_id": 55,
            "from_seat": 3,
            "callers": [
                {"seat": 0, "call_type": "pon", "options": None},
                {"seat": 0, "call_type": "chi", "options": [[57, 63]]},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result["caller_seat"] == 0
        assert result["available_calls"] == [
            {"call_type": "pon"},
            {"call_type": "chi", "options": [[57, 63]]},
        ]
