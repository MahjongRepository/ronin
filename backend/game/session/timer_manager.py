from collections.abc import Callable
from typing import TYPE_CHECKING

from game.logic.enums import TimeoutType

if TYPE_CHECKING:
    from game.session.models import Participant


TimeoutCallback = Callable[["Participant", TimeoutType], None]


class TimerManager:
    """
    Arm participants' timers with the session's timeout callback.

    Each participant owns its `TurnTimer` for the whole game; this class only arms it. A fired timer detaches its task
    from its `TurnTimer` and runs the callback synchronously inside that task, so a running callback is never cancelled
    and never observed half done.
    """

    def __init__(self, on_timeout: TimeoutCallback) -> None:
        self._on_timeout = on_timeout

    def start_turn_timer(self, participant: Participant) -> None:
        participant.timer.start_turn_timer(lambda: self._on_timeout(participant, TimeoutType.TURN))

    def start_meld_timer(self, participant: Participant) -> None:
        participant.timer.start_meld_timer(lambda: self._on_timeout(participant, TimeoutType.MELD))

    def start_round_advance_timer(self, participant: Participant) -> None:
        participant.timer.start_fixed_timer(
            participant.game.timer_config.round_advance_timeout_seconds,
            lambda: self._on_timeout(participant, TimeoutType.ROUND_ADVANCE),
        )
