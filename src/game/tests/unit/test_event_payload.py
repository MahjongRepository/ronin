import pytest

from game.logic.events import (
    BroadcastTarget,
    DiscardEvent,
    DrawEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.messaging.event_payload import service_event_payload, service_event_target


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


class TestServiceEventTarget:
    """Tests for target string serialization."""

    def test_broadcast_target(self):
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_tsumogiri=False, is_riichi=False),
            target=BroadcastTarget(),
        )
        assert service_event_target(event) == "all"

    def test_seat_target(self):
        event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(seat=2, tile_id=5, target="seat_2"),
            target=SeatTarget(seat=2),
        )
        assert service_event_target(event) == "seat_2"

    def test_seat_target_various_seats(self):
        for seat in range(4):
            event = ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=seat, tile_id=1, target=f"seat_{seat}"),
                target=SeatTarget(seat=seat),
            )
            assert service_event_target(event) == f"seat_{seat}"

    def test_unknown_target_raises(self):
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_tsumogiri=False, is_riichi=False),
            target=BroadcastTarget(),
        )
        # Replace target with an unexpected type to trigger the error branch
        event.__dict__["target"] = "unknown"
        with pytest.raises(ValueError, match="Unknown target type"):
            service_event_target(event)
