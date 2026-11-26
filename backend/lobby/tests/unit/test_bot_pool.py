from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.bot_pool import BotPool
from tests.conftest import make_player

if TYPE_CHECKING:
    from app.players import LobbyPlayer


def _no_conflict(_user_id: str) -> str | None:
    return None


def _make_bot(user_id: str, connection_id: str) -> LobbyPlayer:
    return make_player(connection_id=connection_id, user_id=user_id, username=f"ai-{user_id}")


@pytest.mark.parametrize(("idle", "asked", "claimed"), [(3, 2, 2), (2, 3, 2)])
def test_bot_pool_claim__when_bots_are_idle__should_claim_up_to_the_asked_number_and_hold_them_in_flight(
    idle, asked, claimed
):
    pool = BotPool(find_conflict=_no_conflict)
    bot_ids = {f"bot{i}" for i in range(idle)}
    for bot_id in sorted(bot_ids):
        pool.add(_make_bot(bot_id, connection_id=f"c-{bot_id}"))

    claimed_ids = {bot.user_id for bot in pool.claim(asked)}
    assert len(claimed_ids) == claimed
    assert claimed_ids <= bot_ids
    assert all(pool.is_claimed(bot_id) and not pool.is_standing_by(bot_id) for bot_id in claimed_ids)
    assert {bot_id for bot_id in bot_ids if pool.is_standing_by(bot_id)} == bot_ids - claimed_ids
    assert pool.has_idle == (idle > claimed)


def test_bot_pool_add__when_the_user_is_already_idle__should_hand_the_entry_to_the_new_connection():
    pool = BotPool(find_conflict=_no_conflict)
    first = _make_bot("bot1", connection_id="c1")
    second = _make_bot("bot1", connection_id="c2")

    assert pool.add(first) is None
    assert pool.add(second) is first

    assert pool.remove("c1") is False
    assert pool.claim(2) == [second]
