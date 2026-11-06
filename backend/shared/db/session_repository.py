from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from shared.dal.models import AuthSession
from shared.dal.session_repository import SessionRepository

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Collection

    from shared.db.connection import Database


class SqliteSessionRepository(SessionRepository):
    """
    SQLite implementation of SessionRepository.

    Every write is awaited, never posted, so a logout cannot be lost. Each create purges expired rows and deletes the
    replaced row in the same transaction as its insert.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, session: AuthSession, *, now: float, replacing_token_hash: str | None) -> None:
        """
        Insert a session, replacing the session with `replacing_token_hash` if any.
        """
        await self._db.submit_write(
            partial(_insert_session, session=session, now=now, replacing_token_hash=replacing_token_hash)
        )

    async def create_guest(  # noqa: PLR0913
        self,
        *,
        token_hash: str,
        user_id: str,
        created_at: float,
        expires_at: float,
        now: float,
        pick_name: Callable[[Collection[str]], str],
        replacing_token_hash: str | None,
    ) -> AuthSession:
        """
        Insert a guest session named by `pick_name` from the names of the live guest sessions, in one transaction.
        """
        return await self._db.submit_write(
            partial(
                _insert_guest_session,
                token_hash=token_hash,
                user_id=user_id,
                created_at=created_at,
                expires_at=expires_at,
                now=now,
                pick_name=pick_name,
                replacing_token_hash=replacing_token_hash,
            )
        )

    async def get(self, token_hash: str, *, now: float) -> AuthSession | None:
        """
        Return the session with this token hash, or None when it is missing or expired.
        """
        return await self._db.submit_read(partial(_select_session, token_hash=token_hash, now=now))

    async def delete(self, token_hash: str) -> None:
        """
        Delete the session with this token hash, if any.
        """
        await self._db.submit_write(partial(_delete_session, token_hash=token_hash))


def _purge_and_replace(conn: sqlite3.Connection, *, now: float, replacing_token_hash: str | None) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    if replacing_token_hash is not None:
        _delete_session(conn, token_hash=replacing_token_hash)


def _insert_row(conn: sqlite3.Connection, session: AuthSession) -> None:
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, username, is_guest, created_at, expires_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            session.token_hash,
            session.user_id,
            session.username,
            int(session.is_guest),
            session.created_at,
            session.expires_at,
        ),
    )


def _insert_session(
    conn: sqlite3.Connection, *, session: AuthSession, now: float, replacing_token_hash: str | None
) -> None:
    _purge_and_replace(conn, now=now, replacing_token_hash=replacing_token_hash)
    _insert_row(conn, session)


def _insert_guest_session(  # noqa: PLR0913
    conn: sqlite3.Connection,
    *,
    token_hash: str,
    user_id: str,
    created_at: float,
    expires_at: float,
    now: float,
    pick_name: Callable[[Collection[str]], str],
    replacing_token_hash: str | None,
) -> AuthSession:
    _purge_and_replace(conn, now=now, replacing_token_hash=replacing_token_hash)
    taken = {row[0] for row in conn.execute("SELECT username FROM sessions WHERE is_guest = 1")}
    session = AuthSession(
        token_hash=token_hash,
        user_id=user_id,
        username=pick_name(taken),
        is_guest=True,
        created_at=created_at,
        expires_at=expires_at,
    )
    _insert_row(conn, session)
    return session


def _select_session(conn: sqlite3.Connection, *, token_hash: str, now: float) -> AuthSession | None:
    row = conn.execute(
        "SELECT token_hash, user_id, username, is_guest, created_at, expires_at FROM sessions"
        " WHERE token_hash = ? AND expires_at > ?",
        (token_hash, now),
    ).fetchone()
    if row is None:
        return None

    token_hash, user_id, username, is_guest, created_at, expires_at = row
    return AuthSession(
        token_hash=token_hash,
        user_id=user_id,
        username=username,
        is_guest=bool(is_guest),
        created_at=created_at,
        expires_at=expires_at,
    )


def _delete_session(conn: sqlite3.Connection, *, token_hash: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
