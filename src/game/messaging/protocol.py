from abc import ABC, abstractmethod
from typing import Any


class ConnectionProtocol(ABC):
    """
    Abstract interface for a client connection.

    This abstraction allows message handling logic to be tested
    without real WebSocket connections.
    """

    @property
    @abstractmethod
    def connection_id(self) -> str:
        """
        Unique identifier for this connection.
        """
        ...

    @abstractmethod
    async def send_json(self, data: dict[str, Any]) -> None:
        """
        Send a JSON message to the client.
        """
        ...

    @abstractmethod
    async def receive_json(self) -> dict[str, Any]:
        """
        Receive a JSON message from the client.
        """
        ...

    @abstractmethod
    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close the connection.
        """
        ...
