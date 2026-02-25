"""In-memory session store with periodic expiry cleanup."""

import asyncio
import contextlib
import time
from uuid import uuid4

import structlog

from shared.auth.models import AccountType, AuthSession

CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
DEFAULT_SESSION_TTL_SECONDS = 86400  # 24 hours

logger = structlog.get_logger()


class AuthSessionStore:
    """In-memory session store with expiry cleanup.

    Sessions are ephemeral — server restart means re-login.
    Call start_cleanup() on app startup and stop_cleanup() on shutdown.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, AuthSession] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

    def create_session(
        self,
        user_id: str,
        username: str,
        account_type: AccountType = AccountType.HUMAN,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> AuthSession:
        """Create a session for an authenticated user."""
        now = time.time()
        session = AuthSession(
            session_id=str(uuid4()),
            user_id=user_id,
            username=username,
            created_at=now,
            expires_at=now + ttl_seconds,
            account_type=account_type,
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> AuthSession | None:
        """Return a valid (non-expired) session, or None."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if time.time() > session.expires_at:
            del self._sessions[session_id]
            return None
        return session

    def delete_session(self, session_id: str) -> None:
        """Remove a session (logout)."""
        self._sessions.pop(session_id, None)

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Return count of removed sessions."""
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now > s.expires_at]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info("cleaned up expired sessions", count=len(expired))
        return len(expired)

    def start_cleanup(self) -> None:
        """Start the periodic cleanup background task."""
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        """Stop the periodic cleanup background task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Periodically remove expired sessions."""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            self.cleanup_expired()
