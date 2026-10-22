import time

import pytest
from starlette.testclient import TestClient

from game.logic.enums import WindName
from game.logic.events import EventType
from game.logic.types import (
    GamePlayerInfo,
    PlayerReconnectState,
    ReconnectionSnapshot,
)
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.app import create_app
from game.session.manager import SessionManager
from game.session.models import Player, SessionData
from game.tests.helpers.websocket import (
    create_pending_game,
    join_game_and_start,
    recv_ws,
    send_ws,
)
from game.tests.mocks import MockConnection, MockGameService
from game.wire.events import EVENT_TYPE_INT


def _make_snapshot(game_id: str = "test_game", seat: int = 0) -> ReconnectionSnapshot:
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
        is_furiten=False,
    )


def _start_game_and_get_ticket(client: TestClient) -> str:
    sm = client.app.state.session_manager
    tickets = create_pending_game(client, game_id="test_game")
    ticket = tickets[0]

    # Player1 joins and starts the game via WebSocket
    with client.websocket_connect("/ws/test_game") as ws:
        join_game_and_start(ws, ticket)

        # Inject a "Player2" mock connection into the game so it survives Player1 leaving
        p2_conn = MockConnection()
        p2_session = sm._session_store.create_session(player_name="Player2", game_id="test_game", token="p2-token")
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
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(game_service=game_service, session_manager=SessionManager(game_service))
        with TestClient(app) as client:
            yield client

    def test_reconnect__when_ticket_valid__should_send_game_reconnected(self, client):
        sm = client.app.state.session_manager
        snapshot = _make_snapshot("test_game", seat=0)
        sm._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        ticket = _start_game_and_get_ticket(client)

        with client.websocket_connect("/ws/test_game") as ws:
            send_ws(
                ws,
                {
                    "t": WireClientMessageType.RECONNECT,
                    "game_ticket": ticket,
                },
            )
            msg = recv_ws(ws)
            assert msg["type"] == SessionMessageType.GAME_RECONNECTED
            assert msg["gid"] == "test_game"
            assert msg["s"] == 0

    def test_reconnect__when_ticket_invalid__should_return_invalid_ticket_error(self, client):
        _start_game_and_get_ticket(client)

        with client.websocket_connect("/ws/test_game") as ws:
            send_ws(
                ws,
                {
                    "t": WireClientMessageType.RECONNECT,
                    "game_ticket": "invalid-ticket-string",
                },
            )
            msg = recv_ws(ws)
            assert msg["type"] == SessionMessageType.ERROR
            assert msg["code"] == SessionErrorCode.INVALID_TICKET

    def test_reconnect__when_game_already_cleaned_up__should_return_game_gone_error(self, client):
        sm = client.app.state.session_manager
        tickets = create_pending_game(client, game_id="test_game")

        # Start and leave via WebSocket (1 human = game gets cleaned up)
        ticket = None
        with client.websocket_connect("/ws/test_game") as ws:
            join_game_and_start(ws, tickets[0])
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
            send_ws(
                ws,
                {
                    "t": WireClientMessageType.RECONNECT,
                    "game_ticket": ticket,
                },
            )
            msg = recv_ws(ws)
            assert msg["type"] == SessionMessageType.ERROR
            assert msg["code"] == SessionErrorCode.RECONNECT_GAME_GONE

    def test_reconnect__when_action_sent_after_reconnect__should_process_it(self, client):
        sm = client.app.state.session_manager
        snapshot = _make_snapshot("test_game", seat=0)
        sm._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        ticket = _start_game_and_get_ticket(client)

        with client.websocket_connect("/ws/test_game") as ws:
            send_ws(
                ws,
                {
                    "t": WireClientMessageType.RECONNECT,
                    "game_ticket": ticket,
                },
            )
            reconnect_msg = recv_ws(ws)
            assert reconnect_msg["type"] == SessionMessageType.GAME_RECONNECTED

            send_ws(
                ws,
                {
                    "t": WireClientMessageType.GAME_ACTION,
                    "a": WireGameAction.DISCARD,
                    "ti": 0,
                },
            )
            action_msg = recv_ws(ws)
            assert action_msg["t"] == EVENT_TYPE_INT[EventType.DRAW]
            assert action_msg["player"] == "Player1"
            assert action_msg["success"] is True
