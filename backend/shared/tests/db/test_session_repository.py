from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

from shared.dal.models import AuthSession
from shared.db.connection import Database
from shared.db.session_repository import SqliteSessionRepository

if TYPE_CHECKING:
    from pathlib import Path


def _session(token_hash: str, *, expires_at: float) -> AuthSession:
    return AuthSession(
        token_hash=token_hash,
        user_id=f"user-{token_hash}",
        username=f"name-{token_hash}",
        is_guest=False,
        created_at=0.0,
        expires_at=expires_at,
    )


async def test_session_repository_create__when_expired_rows_exist__should_delete_them_and_keep_live_ones(
    tmp_path: Path,
):
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    await db.open()
    repo = SqliteSessionRepository(db)
    try:
        await repo.create(_session("expired", expires_at=100.0), now=0.0, replacing_token_hash=None)
        await repo.create(_session("live", expires_at=300.0), now=0.0, replacing_token_hash=None)

        await repo.create(_session("new", expires_at=400.0), now=200.0, replacing_token_hash=None)
    finally:
        await db.close()

    with closing(sqlite3.connect(db_path)) as conn:
        stored = conn.execute("SELECT token_hash FROM sessions ORDER BY token_hash").fetchall()
    assert stored == [("live",), ("new",)]
