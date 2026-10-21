from game.logic.events import EventType
from game.wire.enums import WireEventType
from shared.lib.melds import EVENT_TYPE_MELD

EVENT_TYPE_INT: dict[EventType, int] = {EventType[name]: WireEventType[name] for name in WireEventType.__members__}

if WireEventType.MELD != EVENT_TYPE_MELD:
    raise RuntimeError(  # pragma: no cover (exhaustive)
        f"WireEventType.MELD ({WireEventType.MELD}) != EVENT_TYPE_MELD ({EVENT_TYPE_MELD})",
    )

if set(EVENT_TYPE_INT.keys()) != set(EventType):
    raise RuntimeError(  # pragma: no cover (exhaustive)
        f"EVENT_TYPE_INT keys {set(EVENT_TYPE_INT.keys())} != EventType members {set(EventType)}",
    )
