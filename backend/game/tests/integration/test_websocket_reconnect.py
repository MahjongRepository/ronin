"""Integration tests for WebSocket reconnection flow over MessagePack transport.

These tests verify the full reconnection lifecycle through the HTTP/WebSocket layer
using starlette TestClient, complementing the unit tests in test_session_reconnect.py.
"""

import time

import pytest
from starlette.testclient import TestClient

from game.logic.enums import GameAction, WindName
from game.logic.events import EventType
from game.logic.types import (
    GamePlayerInfo,
    PlayerReconnectState,
    ReconnectionSnapshot,
)
from game.messaging.encoder import decode, encode
from game.messaging.event_payload import EVENT_TYPE_INT
from game.messaging.types import ClientMessageType, SessionErrorCode, SessionMessageType
from game.server.app import create_app
from game.session.models import Player, SessionData
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockConnection, MockGameService


def _make_snapshot(game_id: str = "test_game", seat: int = 0) -> ReconnectionSnapshot:
    """Build a minimal ReconnectionSnapshot for integration tests."""
    return ReconnectionSnapshot(
        game_id=game_id,
        players=[
            GamePlayerInfo(seat=0, name="Player1", is_ai_player=False),
            GamePlayerInfo(seat=1, name="AI", is_ai_player=True),
            GamePlayerInfo(seat=2, name="AI", is_ai_player=True),
            GamePlayerInfo(seat=3, name="AI", is_ai_player=True),
        ],
        dealer_seat=0,
        dealer_dice=((1, 2), (3, 4)),
        seat=seat,
        round_wind=WindName.EAST,
        round_number=1,
        current_player_seat=0,
        dora_indicators=[0],
        honba_sticks=0,
        riichi_sticks=0,
        my_tiles=[1, 2, 3],
        dice=(3, 4),
        tiles_remaining=70,
        player_states=[
            PlayerReconnectState(seat=i, score=25000, discards=[], melds=[], is_riichi=False) for i in range(4)
        ],
    )


def _send(ws, data: dict) -> None:
    ws.send_bytes(encode(data))


def _recv(ws) -> dict:
    return decode(ws.receive_bytes())


def _join_room_and_start(ws, room_id: str, player_name: str) -> list[dict]:
    """Join a room (1 human + 3 AI), ready up, drain startup messages."""
    ticket = make_test_game_ticket(player_name, room_id)
    _send(
        ws,
        {
            "type": ClientMessageType.JOIN_ROOM,
            "room_id": room_id,
            "game_ticket": ticket,
        },
    )
    messages = [_recv(ws)]  # room_joined

    _send(ws, {"type": ClientMessageType.SET_READY, "ready": True})
    while True:
        msg = _recv(ws)
        messages.append(msg)
        if msg.get("t") in (EVENT_TYPE_INT[EventType.ROUND_STARTED], EVENT_TYPE_INT[EventType.DRAW]):
            break
    return messages


def _start_game_and_get_ticket(client: TestClient) -> str:
    """Start a 1-player game over WebSocket and disconnect to get the game ticket.

    Injects a second mock player into the game AFTER start so the game
    survives when Player1 disconnects via WebSocket close.
    Returns the game ticket string (which is the session token).
    """

    sm = client.app.state.session_manager
    sm.create_room("test_game", num_ai_players=3)

    # Player1 joins and starts the game via WebSocket
    with client.websocket_connect("/ws/test_game") as ws:
        _join_room_and_start(ws, "test_game", "Player1")

        # Grab Player1's session token (= the game ticket used during join)
        ticket = None
        for session in sm._session_store._sessions.values():
            if session.player_name == "Player1" and session.game_id == "test_game":
                ticket = session.session_token
                break
        assert ticket is not None

        # Inject a "Player2" mock connection into the game so it survives Player1 leaving
        p2_conn = MockConnection()
        sm.register_connection(p2_conn)
        p2_session = sm._session_store.create_session("Player2", "test_game", token="p2-token")
        sm._session_store.bind_seat(p2_session.session_token, 1)
        game = sm._games["test_game"]
        p2_player = Player(
            connection=p2_conn,
            name="Player2",
            session_token=p2_session.session_token,
            game_id="test_game",
            seat=1,
        )
        game.players[p2_conn.connection_id] = p2_player
        sm._players[p2_conn.connection_id] = p2_player

    # WebSocket close triggers leave_game for Player1; game survives via Player2
    assert sm.get_game("test_game") is not None

    # Stub get_game_state to return None so _send_turn_state_on_reconnect
    # skips cleanly (MockGameService's _MockGameState lacks round_state)
    sm._game_service.get_game_state = lambda gid: None

    return ticket


class TestWebSocketReconnect:
    """Integration tests for reconnection over WebSocket transport."""

    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def test_reconnect_full_flow(self, client):
        """Full reconnect flow over WebSocket: receive game_reconnected with game state."""
        sm = client.app.state.session_manager
        snapshot = _make_snapshot("test_game", seat=0)
        sm._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        ticket = _start_game_and_get_ticket(client)

        with client.websocket_connect("/ws/test_game") as ws:
            _send(
                ws,
                {
                    "type": ClientMessageType.RECONNECT,
                    "room_id": "test_game",
                    "game_ticket": ticket,
                },
            )

            msg = _recv(ws)
            assert msg["type"] == SessionMessageType.GAME_RECONNECTED
            assert msg["game_id"] == "test_game"
            assert msg["seat"] == 0

    def test_reconnect_invalid_ticket_over_websocket(self, client):
        """Reconnect with invalid ticket returns structured error over WebSocket."""
        _start_game_and_get_ticket(client)

        with client.websocket_connect("/ws/test_game") as ws:
            _send(
                ws,
                {
                    "type": ClientMessageType.RECONNECT,
                    "room_id": "test_game",
                    "game_ticket": "invalid-ticket-string",
                },
            )

            msg = _recv(ws)
            assert msg["type"] == SessionMessageType.ERROR
            assert msg["code"] == SessionErrorCode.INVALID_TICKET

    def test_reconnect_game_gone_over_websocket(self, client):
        """Reconnect after game cleanup returns game_gone error."""
        sm = client.app.state.session_manager
        sm.create_room("test_game", num_ai_players=3)

        # Start and leave via WebSocket (1 human = game gets cleaned up)
        # Capture the ticket used during join from the session store before the game cleans up.
        ticket = None
        with client.websocket_connect("/ws/test_game") as ws:
            _join_room_and_start(ws, "test_game", "Player1")
            for session in sm._session_store._sessions.values():
                if session.player_name == "Player1" and session.game_id == "test_game":
                    ticket = session.session_token
                    break
            assert ticket is not None

        # game was cleaned up (last human left)
        assert sm.get_game("test_game") is None

        # re-inject a disconnected session for the gone game (keyed by the ticket string)
        session = SessionData(
            session_token=ticket,
            player_name="Player1",
            game_id="test_game",
            seat=0,
            disconnected_at=time.monotonic(),
        )
        sm._session_store._sessions[ticket] = session

        with client.websocket_connect("/ws/test_game") as ws:
            _send(
                ws,
                {
                    "type": ClientMessageType.RECONNECT,
                    "room_id": "test_game",
                    "game_ticket": ticket,
                },
            )

            msg = _recv(ws)
            assert msg["type"] == SessionMessageType.ERROR
            assert msg["code"] == SessionErrorCode.RECONNECT_GAME_GONE

    def test_reconnect_path_injects_room_id(self, client):
        """WebSocket path param overrides room_id in reconnect message payload."""
        sm = client.app.state.session_manager
        snapshot = _make_snapshot("test_game", seat=0)
        sm._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        ticket = _start_game_and_get_ticket(client)

        with client.websocket_connect("/ws/test_game") as ws:
            # Send reconnect with a wrong room_id; the path param overrides it
            _send(
                ws,
                {
                    "type": ClientMessageType.RECONNECT,
                    "room_id": "ignored_value",
                    "game_ticket": ticket,
                },
            )

            msg = _recv(ws)
            assert msg["type"] == SessionMessageType.GAME_RECONNECTED
            assert msg["game_id"] == "test_game"

    def test_reconnect_then_game_action(self, client):
        """Player reconnects and can send game actions over the same WebSocket."""
        sm = client.app.state.session_manager
        snapshot = _make_snapshot("test_game", seat=0)
        sm._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        ticket = _start_game_and_get_ticket(client)

        with client.websocket_connect("/ws/test_game") as ws:
            _send(
                ws,
                {
                    "type": ClientMessageType.RECONNECT,
                    "room_id": "test_game",
                    "game_ticket": ticket,
                },
            )

            reconnect_msg = _recv(ws)
            assert reconnect_msg["type"] == SessionMessageType.GAME_RECONNECTED

            _send(
                ws,
                {
                    "type": ClientMessageType.GAME_ACTION,
                    "action": GameAction.DISCARD,
                    "tile_id": 0,
                },
            )

            action_msg = _recv(ws)
            assert action_msg["t"] == EVENT_TYPE_INT[EventType.DRAW]
            assert action_msg["player"] == "Player1"
            assert action_msg["success"] is True
