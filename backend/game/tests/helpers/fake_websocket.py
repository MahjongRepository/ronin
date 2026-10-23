from typing import TYPE_CHECKING, Any

from game.messaging.encoder import decode, encode
from shared.tests.helpers.fake_websocket import FakeAsgiClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.types import Message


class FakeWebSocketClient(FakeAsgiClient):
    def __init__(self, game_id: str = "game1") -> None:
        super().__init__(
            {"type": "websocket", "path": f"/ws/{game_id}", "path_params": {"game_id": game_id}, "headers": []}
        )

    @property
    def messages(self) -> list[dict[str, Any]]:
        return [item for item in self.written if isinstance(item, dict)]

    def send(self, data: dict[str, Any]) -> None:
        self.send_frame({"type": "websocket.receive", "bytes": encode(data)})

    async def wait_for_message(self, predicate: Callable[[dict[str, Any]], bool]) -> None:
        async with self.written_changed:
            await self.written_changed.wait_for(lambda: any(predicate(message) for message in self.messages))

    def read_frame(self, message: Message) -> object:
        return decode(message["bytes"])
