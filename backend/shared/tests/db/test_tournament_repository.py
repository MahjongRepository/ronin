from __future__ import annotations

from typing import TYPE_CHECKING

from shared.dal.models import Tournament
from shared.db.connection import Database
from shared.db.tournament_repository import SqliteTournamentRepository

if TYPE_CHECKING:
    from pathlib import Path


def _tournament(tournament_id: str, *, owner_user_id: str, created_at: float) -> Tournament:
    return Tournament(
        id=tournament_id, name=f"name-{tournament_id}", owner_user_id=owner_user_id, created_at=created_at
    )


async def test_list_tournaments_by_owner__when_two_owners__should_return_only_own_newest_first(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    await db.open()
    repo = SqliteTournamentRepository(db)
    older = _tournament("older", owner_user_id="alice", created_at=100.0)
    newer = _tournament("newer", owner_user_id="alice", created_at=200.0)
    try:
        await repo.create_tournament(older)
        await repo.create_tournament(_tournament("other", owner_user_id="bob", created_at=150.0))
        await repo.create_tournament(newer)

        owned = await repo.list_tournaments_by_owner("alice")
    finally:
        await db.close()

    assert owned == [newer, older]
