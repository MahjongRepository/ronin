from abc import ABC, abstractmethod
from typing import Any

from game.messaging.encoder import encode


class ConnectionProtocol(ABC):
    """
    Abstract interface for a client connection.

    This abstraction allows message handling logic to be tested without real WebSocket connections. Uses MessagePack
    binary protocol. Sends and closes are queued, never awaited, so no caller waits on a client's socket.
    """

    @property
    @abstractmethod
    def connection_id(self) -> str:
        """
        Unique identifier for this connection.
        """
        ...

    @property
    @abstractmethod
    def game_id(self) -> str:
        """
        Game ID from the WebSocket URL path (e.g., /ws/{game_id}).
        """
        ...

    @abstractmethod
    def send_bytes(self, data: bytes) -> None:
        """
        Queue raw bytes for the client without waiting on the socket.

        Never raises for a dead or slow socket: what cannot be delivered is dropped, and the connection's own receive
        reports it gone.
        """
        ...

    @abstractmethod
    async def receive_bytes(self) -> bytes:
        """
        Receive raw bytes from the client.

        Raises ConnectionError when the socket is gone and DecodeError for a frame that carries no bytes.
        """
        ...

    @abstractmethod
    def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Queue a close after everything already sent; idempotent, and nothing is sent after it.
        """
        ...

    def send_message(self, data: dict[str, Any]) -> None:
        """
        Encode a message with MessagePack and queue it; an encoding error raises here, at the caller.
        """
        self.send_bytes(encode(data))
