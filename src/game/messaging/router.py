import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from game.messaging.types import (
    ChatMessage,
    ErrorMessage,
    GameActionMessage,
    JoinGameMessage,
    LeaveGameMessage,
    PingMessage,
    SessionErrorCode,
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

        if isinstance(message, JoinGameMessage):
            await self._session_manager.join_game(
                connection=connection,
                game_id=message.game_id,
                player_name=message.player_name,
            )
        elif isinstance(message, LeaveGameMessage):
            await self._session_manager.leave_game(connection)
        elif isinstance(message, GameActionMessage):
            try:
                await self._session_manager.handle_game_action(
                    connection=connection,
                    action=message.action,
                    data=message.data,
                )
            except (ValueError, KeyError, TypeError) as e:
                logger.exception(f"action failed for {connection.connection_id}")
                await connection.send_message(
                    ErrorMessage(code=SessionErrorCode.ACTION_FAILED, message=str(e)).model_dump()
                )
            except Exception:  # pragma: no cover
                logger.exception(f"fatal error during game action for {connection.connection_id}")
                await self._session_manager.close_game_on_error(connection)
        elif isinstance(message, PingMessage):
            await self._session_manager.handle_ping(connection)
        elif isinstance(message, ChatMessage):
            await self._session_manager.broadcast_chat(
                connection=connection,
                text=message.text,
            )

    async def handle_connect(self, connection: ConnectionProtocol) -> None:
        self._session_manager.register_connection(connection)

    async def handle_disconnect(self, connection: ConnectionProtocol) -> None:
        await self._session_manager.leave_game(connection, notify_player=False)
        self._session_manager.unregister_connection(connection)
