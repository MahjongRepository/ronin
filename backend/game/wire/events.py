from game.logic.events import EventType
from game.wire.enums import WireEventType
from shared.lib.melds import EVENT_TYPE_MELD

EVENT_TYPE_INT: dict[EventType, int] = {event_type: WireEventType[event_type.name] for event_type in EventType}

if WireEventType.MELD != EVENT_TYPE_MELD:
    raise RuntimeError(  # pragma: no cover (exhaustive)
        f"WireEventType.MELD ({WireEventType.MELD}) != EVENT_TYPE_MELD ({EVENT_TYPE_MELD})",
    )

if set(WireEventType) - set(EVENT_TYPE_INT.values()) != {WireEventType.DRAW_NOTICE}:
    raise RuntimeError(  # pragma: no cover (exhaustive)
        f"WireEventType members without an EventType {set(WireEventType) - set(EVENT_TYPE_INT.values())} "
        f"!= {{{WireEventType.DRAW_NOTICE!r}}}",
    )
