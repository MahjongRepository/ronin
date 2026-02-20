import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from game.logic.enums import GameAction
from game.logic.exceptions import GameRuleError
from game.messaging.types import (
    ChatMessage,
    ChiMessage,
    DiscardMessage,
    ErrorMessage,
    JoinRoomMessage,
    KanMessage,
    LeaveRoomMessage,
    NoDataActionMessage,
    PingMessage,
    PonMessage,
    ReconnectMessage,
    RiichiMessage,
    SessionErrorCode,
    SetReadyMessage,
    parse_client_message,
)
from shared.auth.game_ticket import GameTicket, verify_game_ticket

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol
    from game.session.manager import SessionManager

logger = logging.getLogger(__name__)


_GAME_ACTION_TYPES = (
    DiscardMessage,
    RiichiMessage,
    PonMessage,
    ChiMessage,
    KanMessage,
    NoDataActionMessage,
)


class MessageRouter:
    """
    Routes incoming messages to appropriate handlers.

    This class contains pure business logic and can be tested
    without real WebSocket connections.
    """

    def __init__(self, session_manager: SessionManager, *, game_ticket_secret: str) -> None:
        self._session_manager = session_manager
        self._game_ticket_secret = game_ticket_secret

    async def handle_message(
        self,
        connection: ConnectionProtocol,
        raw_message: dict[str, Any],
    ) -> None:
        try:
            message = parse_client_message(raw_message)
        except (ValidationError, KeyError, TypeError, ValueError) as e:
            logger.warning("invalid message from %s: %s", connection.connection_id, e)
            await connection.send_message(
                ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=str(e)).model_dump(),
            )
            return

        if isinstance(message, JoinRoomMessage):
            await self._handle_join_room(connection, message)
        elif isinstance(message, LeaveRoomMessage):
            await self._session_manager.leave_room(connection)
        elif isinstance(message, SetReadyMessage):
            await self._session_manager.set_ready(connection, ready=message.ready)
        elif isinstance(message, _GAME_ACTION_TYPES):
            await self._handle_game_action(connection, message)
        elif isinstance(message, ReconnectMessage):
            await self._handle_reconnect(connection, message)
        elif isinstance(message, PingMessage):
            await self._session_manager.handle_ping(connection)
        elif isinstance(message, ChatMessage):
            await self._handle_chat(connection, message)

    async def _verify_ticket(
        self,
        connection: ConnectionProtocol,
        ticket_str: str,
        room_id: str,
    ) -> GameTicket | None:
        """Verify game ticket signature, expiry, and room binding. Send error on failure."""
        ticket = verify_game_ticket(ticket_str, self._game_ticket_secret)
        if ticket is None:
            await self._send_ticket_error(connection, "Invalid game ticket")
            return None
        if ticket.room_id != room_id:
            await self._send_ticket_error(connection, "Ticket room_id mismatch")
            return None
        return ticket

    async def _send_ticket_error(self, connection: ConnectionProtocol, message: str) -> None:
        """Send an INVALID_TICKET error to the connection."""
        await connection.send_message(
            ErrorMessage(code=SessionErrorCode.INVALID_TICKET, message=message).model_dump(),
        )

    async def _handle_join_room(
        self,
        connection: ConnectionProtocol,
        message: JoinRoomMessage,
    ) -> None:
        """Verify game ticket and join the room."""
        ticket = await self._verify_ticket(connection, message.game_ticket, message.room_id)
        if ticket is None:
            return
        await self._session_manager.join_room(
            connection=connection,
            room_id=message.room_id,
            player_name=ticket.username,
            user_id=ticket.user_id,
            session_token=message.game_ticket,
        )

    async def _handle_reconnect(
        self,
        connection: ConnectionProtocol,
        message: ReconnectMessage,
    ) -> None:
        """Verify game ticket and attempt reconnection."""
        ticket = await self._verify_ticket(connection, message.game_ticket, message.room_id)
        if ticket is None:
            return
        await self._session_manager.reconnect(
            connection=connection,
            room_id=message.room_id,
            session_token=message.game_ticket,
        )

    async def _handle_game_action(
        self,
        connection: ConnectionProtocol,
        message: DiscardMessage | RiichiMessage | PonMessage | ChiMessage | KanMessage | NoDataActionMessage,
    ) -> None:
        """Route a game action message, handling expected and fatal errors."""
        try:
            data = message.model_dump(exclude={"t", "a"})
            action = GameAction[message.a.name]
            await self._session_manager.handle_game_action(
                connection=connection,
                action=action,
                data=data,
            )
        except (GameRuleError, ValueError, KeyError, TypeError) as e:
            logger.warning("action failed for %s: %s", connection.connection_id, e)
            await connection.send_message(
                ErrorMessage(code=SessionErrorCode.ACTION_FAILED, message=str(e)).model_dump(),
            )
        except Exception:
            logger.exception("fatal error during game action for %s", connection.connection_id)
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
