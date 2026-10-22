from contextlib import contextmanager
from typing import TYPE_CHECKING

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
from game.tests.helpers.session import make_session_manager
from game.tests.helpers.websocket import (
    create_pending_game,
    join_game_and_start,
    recv_ws,
    send_ws,
)
from game.wire.events import EVENT_TYPE_INT

if TYPE_CHECKING:
    from collections.abc import Generator


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


@contextmanager
def _game_with_player1_dropped(client: TestClient) -> Generator[str]:
    tickets = create_pending_game(client, game_id="test_game", num_ai_players=2)
    with client.websocket_connect("/ws/test_game") as player2:
        send_ws(player2, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": tickets[1]})
        with client.websocket_connect("/ws/test_game") as player1:
            join_game_and_start(player1, tickets[0])

        assert client.app.state.session_manager.get_game("test_game") is not None
        yield tickets[0]


class TestWebSocketReconnect:
    @pytest.fixture
    def client(self):
        session_manager = make_session_manager()
        app = create_app(game_service=session_manager._game_service, session_manager=session_manager)
        with TestClient(app) as client:
            yield client

    def test_reconnect__when_ticket_valid__should_send_game_reconnected(self, client):
        sm = client.app.state.session_manager
        snapshot = _make_snapshot("test_game", seat=0)
        sm._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        with _game_with_player1_dropped(client) as ticket, client.websocket_connect("/ws/test_game") as ws:
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
        with _game_with_player1_dropped(client), client.websocket_connect("/ws/test_game") as ws:
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

    def test_reconnect__when_game_already_ended__should_return_no_session_error(self, client):
        tickets = create_pending_game(client, game_id="test_game")
        with client.websocket_connect("/ws/test_game") as ws:
            join_game_and_start(ws, tickets[0])

        assert client.app.state.session_manager.get_game("test_game") is None

        with client.websocket_connect("/ws/test_game") as ws:
            send_ws(ws, {"t": WireClientMessageType.RECONNECT, "game_ticket": tickets[0]})
            msg = recv_ws(ws)
            assert msg["type"] == SessionMessageType.ERROR
            assert msg["code"] == SessionErrorCode.RECONNECT_NO_SESSION

    def test_reconnect__when_action_sent_after_reconnect__should_process_it(self, client):
        sm = client.app.state.session_manager
        snapshot = _make_snapshot("test_game", seat=0)
        sm._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        with _game_with_player1_dropped(client) as ticket, client.websocket_connect("/ws/test_game") as ws:
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
                    "wi": reconnect_msg["wi"],
                    "a": WireGameAction.DISCARD,
                    "ti": 0,
                },
            )
            action_msg = recv_ws(ws)
            assert action_msg["t"] == EVENT_TYPE_INT[EventType.DRAW]
            assert action_msg["seat"] == 0
            assert action_msg["success"] is True
