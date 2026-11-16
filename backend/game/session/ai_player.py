from typing import TYPE_CHECKING

from game.engine import Ron, Tsumo

if TYPE_CHECKING:
    from game.engine import Action, Decision

AI_WINS = (Tsumo(), Ron())


def choose_ai_action(decision: Decision) -> Action:
    """
    Choose an AI player's answer to its seat's decision: a tsumo or a ron when it is legal, otherwise the decision's
    default, the default discard on a turn and a pass on a call, so it never calls, declares riichi or calls kyuushu.
    """
    return next((win for win in AI_WINS if win in decision.legal), decision.default)
