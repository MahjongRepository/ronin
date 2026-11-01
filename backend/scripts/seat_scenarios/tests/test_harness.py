from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from game.messaging.types import SessionErrorCode
from game.tests.helpers.hands import tile_copies
from scripts.replay_fixtures.staged_game import ScenarioError, StagedWall, tile
from scripts.seat_scenarios.harness import seated_game

if TYPE_CHECKING:
    from collections.abc import Sequence

PLAYER = "Alice"
KYUUSHU_HANDS = (
    tile_copies(2, man="258", pin="258", sou="258", honors="1234"),
    tile_copies(0, man="159", pin="159", sou="159", honors="1234"),
    tile_copies(3, man="258", pin="258", sou="258", honors="1234"),
    tile_copies(1, man="2345678", pin="2346", sou="23"),
)
DEALER_DRAW = tile(0, honors="5")
ALICE_DRAW = tile(1, honors="5")


def _play_kyuushu_into_next_round(staged: StagedWall, later_rounds: Sequence[StagedWall] = ()) -> None:
    with seated_game("harness-check", staged, players=(PLAYER,), later_rounds=later_rounds) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.kyuushu(at=5)
        alice.confirm_round(at=6)
        game.wait_until(7)


def test_seated_game__when_a_staged_draw_names_another_seat__should_fail_naming_the_draw():
    misseated = StagedWall(hands=KYUUSHU_HANDS, draws=((0, DEALER_DRAW), (3, ALICE_DRAW)))

    with pytest.raises(ScenarioError, match=r"seat 1 drew staged draw 1 \(staged for seat 3\)"):
        _play_kyuushu_into_next_round(misseated)


def test_seated_game__when_a_later_round_names_another_dealer__should_fail_naming_the_dealer():
    first_round = StagedWall(hands=KYUUSHU_HANDS, draws=((0, DEALER_DRAW), (1, ALICE_DRAW)))
    misdealt = StagedWall(hands=KYUUSHU_HANDS, dealer=1)

    with pytest.raises(ScenarioError, match="later round 0 was staged for dealer 1, not 0"):
        _play_kyuushu_into_next_round(first_round, later_rounds=(misdealt,))


def _resync_after_the_deal_expecting_game_not_started() -> None:
    staged = StagedWall(hands=KYUUSHU_HANDS, draws=((0, DEALER_DRAW), (1, ALICE_DRAW)))
    with seated_game("harness-check", staged, players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.resync(at=4, refused_with=SessionErrorCode.GAME_NOT_STARTED)


def test_seated_game__when_an_expected_refusal_never_comes__should_fail_naming_it():
    with pytest.raises(ScenarioError, match="never refused with game_not_started"):
        _resync_after_the_deal_expecting_game_not_started()
