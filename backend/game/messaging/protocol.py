"""Abstract connection protocol for MessagePack binary communication."""

from abc import ABC, abstractmethod
from typing import Any

from game.messaging.encoder import decode, encode


class ConnectionProtocol(ABC):
    """
    Abstract interface for a client connection.

    This abstraction allows message handling logic to be tested
    without real WebSocket connections. Uses MessagePack binary protocol.
    """

    @property
    @abstractmethod
    def connection_id(self) -> str:
        """Unique identifier for this connection."""
        ...

    @property
    @abstractmethod
    def game_id(self) -> str:
        """Game ID from the WebSocket URL path (e.g., /ws/{game_id})."""
        ...

    @abstractmethod
    async def send_bytes(self, data: bytes) -> None:
        """
        Send raw bytes to the client.
        """
        ...

    @abstractmethod
    async def receive_bytes(self) -> bytes:
        """
        Receive raw bytes from the client.
        """
        ...

    @abstractmethod
    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close the connection.
        """
        ...

    async def send_message(self, data: dict[str, Any]) -> None:
        """
        Send a message to the client using MessagePack encoding.
        """
        await self.send_bytes(encode(data))

    async def receive_message(self) -> dict[str, Any]:
        """
        Receive a message from the client using MessagePack decoding.
        """
        raw = await self.receive_bytes()
        return decode(raw)
