from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from app.queued_websocket import QueuedWebSocket

REVOKED_CLOSE_CODE = 4001
REVOKED_CLOSE_REASON = "credential_revoked"


class CredentialSockets:
    """
    The open lobby sockets by the hash of the session token or API key that admitted them.

    A socket authenticates once, at its handshake, so revoking a credential (a logout, a replaced session, a rotated
    key) would leave its open sockets acting for the account; closing them here ends that. The closes are enqueued, so
    each socket's handler leaves through its normal disconnect path. In-process only: a script that rotates a key in
    another process closes nothing, and a session that merely expires keeps its open sockets.
    """

    def __init__(self) -> None:
        self._sockets: dict[str, set[QueuedWebSocket]] = {}

    @contextlib.contextmanager
    def admitted(self, credential_hash: str, connection: QueuedWebSocket) -> Generator[None]:
        """
        Hold the connection under its credential while the block runs.
        """
        self._sockets.setdefault(credential_hash, set()).add(connection)
        try:
            yield
        finally:
            connections = self._sockets.get(credential_hash)
            if connections is not None:
                connections.discard(connection)
                if not connections:
                    del self._sockets[credential_hash]

    def close_all(self, credential_hash: str) -> None:
        """
        Close every open socket the revoked credential admitted.
        """
        for connection in self._sockets.pop(credential_hash, set()):
            connection.close(code=REVOKED_CLOSE_CODE, reason=REVOKED_CLOSE_REASON)
