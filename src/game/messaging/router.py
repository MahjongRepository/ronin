from typing import TYPE_CHECKING, Any

from game.messaging.types import (
    ClientMessageType,
    ErrorMessage,
    parse_client_message,
)

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol
    from game.session.manager import SessionManager


class MessageRouter:
    """
    Routes incoming messages to appropriate handlers.

    This class contains pure business logic and can be tested
    without real WebSocket connections.
    """

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    async def handle_message(
        self,
        connection: ConnectionProtocol,
        raw_message: dict[str, Any],
    ) -> None:
        try:
            message = parse_client_message(raw_message)
        except Exception as e:
            await connection.send_json(ErrorMessage(code="invalid_message", message=str(e)).model_dump())
            return

        match message.type:
            case ClientMessageType.JOIN_GAME:
                await self._session_manager.join_game(
                    connection=connection,
                    game_id=message.game_id,
                    player_name=message.player_name,
                )
            case ClientMessageType.LEAVE_GAME:
                await self._session_manager.leave_game(connection)
            case ClientMessageType.GAME_ACTION:
                await self._session_manager.handle_game_action(
                    connection=connection,
                    action=message.action,
                    data=message.data,
                )
            case ClientMessageType.CHAT:
                await self._session_manager.broadcast_chat(
                    connection=connection,
                    text=message.text,
                )

    async def handle_connect(self, connection: ConnectionProtocol) -> None:
        self._session_manager.register_connection(connection)

    async def handle_disconnect(self, connection: ConnectionProtocol) -> None:
        await self._session_manager.leave_game(connection, notify_player=False)
        self._session_manager.unregister_connection(connection)
