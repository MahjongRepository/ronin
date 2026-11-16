import pytest

from game.engine import (
    CallOpportunity,
    CallSource,
    Chi,
    Decision,
    Discard,
    Kan,
    KanType,
    Kyuushu,
    Pass,
    Pon,
    Riichi,
    Ron,
    Tsumo,
    TurnAfterDraw,
)
from game.session.ai_player import choose_ai_action
from game.tests.helpers.hands import tile_copies

DRAWN = tile_copies(0, sou="6")[0]
CALLED = tile_copies(1, pin="5")[0]
TURN = TurnAfterDraw(drawn=DRAWN, rinshan=False, haitei=False)
DISCARD_CALL = CallOpportunity(tile=CALLED, from_seat=0, source=CallSource.DISCARD, houtei=False)
ADDED_KAN_CALL = CallOpportunity(tile=CALLED, from_seat=0, source=CallSource.ADDED_KAN, houtei=False)
DEFAULT_DISCARD = Discard(tile=DRAWN)


def _decision(context: TurnAfterDraw | CallOpportunity, legal: tuple, default: Discard | Pass) -> Decision:
    return Decision(seat=1, context=context, legal=legal, default=default)


@pytest.mark.parametrize(
    ("decision", "win"),
    [
        (_decision(TURN, (DEFAULT_DISCARD, Riichi(tile=DRAWN), Tsumo()), DEFAULT_DISCARD), Tsumo()),
        (_decision(DISCARD_CALL, (Ron(), Pon(), Pass()), Pass()), Ron()),
        (_decision(ADDED_KAN_CALL, (Ron(), Pass()), Pass()), Ron()),
    ],
    ids=["tsumo", "ron_on_a_discard", "chankan_ron"],
)
def test_choose_ai_action__when_a_win_is_legal__should_take_it(decision, win):
    assert choose_ai_action(decision) == win


@pytest.mark.parametrize(
    "decision",
    [
        _decision(
            TURN,
            (DEFAULT_DISCARD, Riichi(tile=DRAWN), Kan(kan_type=KanType.CLOSED, tile=DRAWN), Kyuushu()),
            DEFAULT_DISCARD,
        ),
        _decision(
            DISCARD_CALL,
            (Kan(kan_type=KanType.OPEN, tile=CALLED), Pon(), Chi(tiles=(CALLED + 4, CALLED + 8)), Pass()),
            Pass(),
        ),
    ],
    ids=["turn", "call"],
)
def test_choose_ai_action__when_no_win_is_legal__should_play_the_default_rather_than_riichi_kan_kyuushu_or_a_call(
    decision,
):
    assert choose_ai_action(decision) == decision.default
