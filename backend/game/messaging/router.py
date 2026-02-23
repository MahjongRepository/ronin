from typing import TYPE_CHECKING, Any

import structlog
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.logic.exceptions import GameRuleError
from game.messaging.types import (
    ChatMessage,
    ChiMessage,
    DiscardMessage,
    ErrorMessage,
    JoinGameMessage,
    KanMessage,
    NoDataActionMessage,
    PingMessage,
    PonMessage,
    ReconnectMessage,
    RiichiMessage,
    SessionErrorCode,
    parse_client_message,
)
from shared.auth.game_ticket import GameTicket, verify_game_ticket

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol
    from game.session.manager import SessionManager

logger = structlog.get_logger()


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
            logger.warning("invalid message", error=str(e))
            await connection.send_message(
                ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=str(e)).model_dump(),
            )
            return

        if isinstance(message, _GAME_ACTION_TYPES):
            await self._handle_game_action(connection, message)
        elif isinstance(message, JoinGameMessage):
            await self._handle_join_game(connection, message)
        elif isinstance(message, ReconnectMessage):
            await self._handle_reconnect(connection, message)
        elif isinstance(message, PingMessage):
            await self._session_manager.handle_ping(connection)
        elif isinstance(message, ChatMessage):
            await self._session_manager.broadcast_chat(connection, text=message.text)

    async def _verify_ticket(
        self,
        connection: ConnectionProtocol,
        ticket_str: str,
        game_id: str,
    ) -> GameTicket | None:
        """Verify game ticket signature, expiry, and game binding. Send error on failure."""
        ticket = verify_game_ticket(ticket_str, self._game_ticket_secret)
        if ticket is None:
            logger.warning("invalid game ticket")
            await self._send_ticket_error(connection, "Invalid game ticket")
            return None
        if ticket.room_id != game_id:
            logger.warning("ticket game_id mismatch", ticket_room_id=ticket.room_id, expected_game_id=game_id)
            await self._send_ticket_error(connection, "Ticket game_id mismatch")
            return None
        return ticket

    async def _send_ticket_error(self, connection: ConnectionProtocol, message: str) -> None:
        """Send an INVALID_TICKET error to the connection."""
        await connection.send_message(
            ErrorMessage(code=SessionErrorCode.INVALID_TICKET, message=message).model_dump(),
        )

    async def _handle_join_game(
        self,
        connection: ConnectionProtocol,
        message: JoinGameMessage,
    ) -> None:
        """Verify game ticket and join a pending game."""
        ticket = await self._verify_ticket(connection, message.game_ticket, connection.game_id)
        if ticket is None:
            return
        await self._session_manager.join_game(
            connection=connection,
            game_id=connection.game_id,
            session_token=message.game_ticket,
        )

    async def _handle_reconnect(
        self,
        connection: ConnectionProtocol,
        message: ReconnectMessage,
    ) -> None:
        """Verify game ticket and attempt reconnection."""
        ticket = await self._verify_ticket(connection, message.game_ticket, connection.game_id)
        if ticket is None:
            return
        await self._session_manager.reconnect(
            connection=connection,
            game_id=connection.game_id,
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
            logger.warning("action failed", error=str(e))
            await connection.send_message(
                ErrorMessage(code=SessionErrorCode.ACTION_FAILED, message=str(e)).model_dump(),
            )
        except Exception:
            logger.exception("fatal error during game action")
            await self._session_manager.close_game_on_error(connection)

    async def handle_connect(self, connection: ConnectionProtocol) -> None:
        self._session_manager.register_connection(connection)

    async def handle_disconnect(self, connection: ConnectionProtocol) -> None:
        await self._session_manager.leave_game(connection, notify_player=False)
        self._session_manager.unregister_connection(connection)
