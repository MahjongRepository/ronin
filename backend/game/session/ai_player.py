from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.engine import Action, Decision


def choose_ai_action(decision: Decision) -> Action:
    """
    Choose an AI player's answer to its seat's decision: the decision's default, the default discard on a turn and a
    pass on a call, so it never wins, calls, declares riichi or calls kyuushu.
    """
    return decision.default
