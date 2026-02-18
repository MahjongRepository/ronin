import time
from uuid import uuid4

from game.session.models import SessionData


class SessionStore:
    """In-memory store for player session data.

    Map session tokens to session data, enabling identity persistence
    across WebSocket connection drops. Session data survives disconnects
    and is cleaned up when the associated game ends.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}  # session_token -> SessionData

    def create_session(self, player_name: str, game_id: str, token: str | None = None) -> SessionData:
        """Create a session for a player joining a game. Return the session data."""
        token = token or str(uuid4())
        session = SessionData(
            session_token=token,
            player_name=player_name,
            game_id=game_id,
        )
        self._sessions[token] = session
        return session

    def bind_seat(self, token: str, seat: int) -> None:
        """Assign a seat number to a session (called at game start)."""
        session = self._sessions.get(token)
        if session is not None:
            session.seat = seat

    def mark_disconnected(self, token: str) -> None:
        """Record the disconnect timestamp for a session."""
        session = self._sessions.get(token)
        if session is not None:
            session.disconnected_at = time.monotonic()

    def remove_session(self, token: str) -> None:
        """Remove a single session by token."""
        self._sessions.pop(token, None)

    def get_session(self, token: str) -> SessionData | None:
        """Look up a session by token."""
        return self._sessions.get(token)

    def mark_reconnected(self, token: str) -> None:
        """Clear disconnect state for a reconnected session."""
        session = self._sessions.get(token)
        if session is not None:
            session.disconnected_at = None

    def prepare_token_rotation(self, token: str) -> str | None:
        """Generate a new token for rotation without removing the old one.

        Returns the new token string, or None if the session doesn't exist.
        The old token remains valid until commit_token_rotation() is called.
        """
        session = self._sessions.get(token)
        if session is None:
            return None
        return str(uuid4())

    def commit_token_rotation(self, old_token: str, new_token: str) -> None:
        """Commit a previously prepared token rotation by swapping old -> new.

        Call this only after the client has received the new token (e.g. after
        a successful send_message). This ensures the old token remains valid
        if the send fails, so the client can retry with its known token.
        """
        session = self._sessions.get(old_token)
        if session is None:
            return
        self._sessions.pop(old_token, None)
        session.session_token = new_token
        self._sessions[new_token] = session

    def cleanup_game(self, game_id: str) -> None:
        """Remove all sessions associated with a game."""
        tokens_to_remove = [token for token, session in self._sessions.items() if session.game_id == game_id]
        for token in tokens_to_remove:
            del self._sessions[token]
