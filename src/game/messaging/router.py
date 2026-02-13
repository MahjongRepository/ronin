import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from game.logic.exceptions import GameRuleError
from game.messaging.types import (
    ChatMessage,
    ErrorMessage,
    GameActionMessage,
    JoinRoomMessage,
    LeaveRoomMessage,
    PingMessage,
    SessionErrorCode,
    SetReadyMessage,
    parse_client_message,
)

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol
    from game.session.manager import SessionManager

logger = logging.getLogger(__name__)


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
        except (ValidationError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"invalid message from {connection.connection_id}: {e}")
            await connection.send_message(
                ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=str(e)).model_dump()
            )
            return

        if isinstance(message, JoinRoomMessage):
            await self._session_manager.join_room(
                connection=connection,
                room_id=message.room_id,
                player_name=message.player_name,
                session_token=message.session_token,
            )
        elif isinstance(message, LeaveRoomMessage):
            await self._session_manager.leave_room(connection)
        elif isinstance(message, SetReadyMessage):
            await self._session_manager.set_ready(connection, ready=message.ready)
        elif isinstance(message, GameActionMessage):
            await self._handle_game_action(connection, message)
        elif isinstance(message, PingMessage):
            await self._session_manager.handle_ping(connection)
        elif isinstance(message, ChatMessage):
            await self._handle_chat(connection, message)

    async def _handle_game_action(self, connection: ConnectionProtocol, message: GameActionMessage) -> None:
        """Route a game action message, handling expected and fatal errors."""
        try:
            await self._session_manager.handle_game_action(
                connection=connection,
                action=message.action,
                data=message.data,
            )
        except (GameRuleError, ValueError, KeyError, TypeError) as e:
            logger.exception(f"action failed for {connection.connection_id}")
            await connection.send_message(
                ErrorMessage(code=SessionErrorCode.ACTION_FAILED, message=str(e)).model_dump()
            )
        except Exception:
            logger.exception(f"fatal error during game action for {connection.connection_id}")
            await self._session_manager.close_game_on_error(connection)

    async def _handle_chat(self, connection: ConnectionProtocol, message: ChatMessage) -> None:
        """Route chat to room or game depending on player state."""
        if self._session_manager.is_in_room(connection.connection_id):
            await self._session_manager.broadcast_room_chat(
                connection=connection,
                text=message.text,
            )
        else:
            await self._session_manager.broadcast_chat(
                connection=connection,
                text=message.text,
            )

    async def handle_connect(self, connection: ConnectionProtocol) -> None:
        self._session_manager.register_connection(connection)

    async def handle_disconnect(self, connection: ConnectionProtocol) -> None:
        await self._session_manager.leave_room(connection, notify_player=False)
        await self._session_manager.leave_game(connection, notify_player=False)
        self._session_manager.unregister_connection(connection)
