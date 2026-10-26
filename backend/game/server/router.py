from typing import TYPE_CHECKING, Any

import structlog
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.messaging.types import (
    ChiMessage,
    DiscardMessage,
    ErrorMessage,
    JoinGameMessage,
    KanMessage,
    NoDataActionMessage,
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

_INVALID_MESSAGE_REASON = "Invalid message"


class MessageRouter:
    """
    Routes incoming messages to appropriate handlers.

    This class contains pure business logic and can be tested without real WebSocket connections. Handling a message is
    synchronous: it runs its session transition in one step. Each handler that reaches a game is an error boundary: any
    exception is a server fault handed to `SessionManager.fail_connection` with the game captured before the call.
    Sends never raise or wait for a dead or slow socket, so a dead socket reaches the endpoint only at receive.
    """

    def __init__(self, session_manager: SessionManager, *, game_ticket_secret: str) -> None:
        self._session_manager = session_manager
        self._game_ticket_secret = game_ticket_secret

    def handle_message(
        self,
        connection: ConnectionProtocol,
        raw_message: dict[str, Any],
    ) -> None:
        try:
            message = parse_client_message(raw_message)
        except ValidationError as e:
            errors = e.errors(include_url=False, include_context=False, include_input=False)
            logger.warning(
                "invalid message",
                error_types=[error["type"] for error in errors],
                error_count=len(errors),
            )
            connection.send_message(
                ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=_INVALID_MESSAGE_REASON).model_dump(),
            )
            return

        if isinstance(message, _GAME_ACTION_TYPES):
            self._handle_game_action(connection, message)
        elif isinstance(message, JoinGameMessage):
            self._handle_join_game(connection, message)
        elif isinstance(message, ReconnectMessage):
            self._handle_reconnect(connection, message)

    def _verify_ticket(
        self,
        connection: ConnectionProtocol,
        ticket_str: str,
        game_id: str,
    ) -> GameTicket | None:
        """
        Verify game ticket signature, expiry, and game binding.

        Send error on failure.
        """
        ticket = verify_game_ticket(ticket_str, self._game_ticket_secret)
        if ticket is None:
            logger.warning("invalid game ticket")
            self._send_ticket_error(connection, "Invalid game ticket")
            return None

        if ticket.room_id != game_id:
            logger.warning("ticket game_id mismatch", ticket_room_id=ticket.room_id, expected_game_id=game_id)
            self._send_ticket_error(connection, "Ticket game_id mismatch")
            return None

        return ticket

    def _send_ticket_error(self, connection: ConnectionProtocol, message: str) -> None:
        """
        Send an INVALID_TICKET error to the connection.
        """
        connection.send_message(
            ErrorMessage(code=SessionErrorCode.INVALID_TICKET, message=message).model_dump(),
        )

    def _handle_join_game(
        self,
        connection: ConnectionProtocol,
        message: JoinGameMessage,
    ) -> None:
        """
        Verify game ticket and join a pending game.
        """
        ticket = self._verify_ticket(connection, ticket_str=message.game_ticket, game_id=connection.game_id)
        if ticket is None:
            return

        game = self._session_manager.get_game(connection.game_id)
        try:
            self._session_manager.join_game(
                connection=connection,
                game_id=connection.game_id,
                session_token=message.game_ticket,
            )
        except Exception as exc:  # noqa: BLE001
            self._session_manager.fail_connection(connection, game, reason="join failed", exc=exc)

    def _handle_reconnect(
        self,
        connection: ConnectionProtocol,
        message: ReconnectMessage,
    ) -> None:
        """
        Verify game ticket and attempt reconnection.
        """
        ticket = self._verify_ticket(connection, ticket_str=message.game_ticket, game_id=connection.game_id)
        if ticket is None:
            return

        game = self._session_manager.get_game(connection.game_id)
        try:
            self._session_manager.reconnect(
                connection=connection,
                game_id=connection.game_id,
                session_token=message.game_ticket,
            )
        except Exception as exc:  # noqa: BLE001
            self._session_manager.fail_connection(connection, game, reason="reconnect failed", exc=exc)

    def _handle_game_action(
        self,
        connection: ConnectionProtocol,
        message: DiscardMessage | RiichiMessage | PonMessage | ChiMessage | KanMessage | NoDataActionMessage,
    ) -> None:
        """
        Route a game action message; an unexpected error is a server fault that fails the connection's game.
        """
        game = self._session_manager.get_connection_game(connection)
        try:
            self._session_manager.handle_game_action(
                connection=connection,
                action=GameAction[message.a.name],
                data=message.model_dump(exclude={"t", "a", "wait_id"}),
                wait_id=message.wait_id,
            )
        except Exception as exc:  # noqa: BLE001
            self._session_manager.fail_connection(connection, game, reason="game action failed", exc=exc)

    def handle_connect(self, connection: ConnectionProtocol) -> None:
        self._session_manager.register_connection(connection)

    def handle_disconnect(self, connection: ConnectionProtocol) -> None:
        """
        Evict a closed connection and take it out of its game; an unexpected error is a server fault failing that game.
        """
        game = self._session_manager.get_connection_game(connection)
        try:
            self._session_manager.disconnect(connection)
        except Exception as exc:  # noqa: BLE001
            self._session_manager.fail_connection(connection, game, reason="disconnect failed", exc=exc)
