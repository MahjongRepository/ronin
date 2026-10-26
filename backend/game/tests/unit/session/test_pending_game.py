import asyncio
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from game.logic.enums import GameAction
from game.logic.events import EventType
from game.messaging.encoder import decode, encode
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.messaging.wire_enums import WireClientMessageType
from game.server.app import create_app
from game.server.router import MessageRouter
from game.server.types import CreateGameRequest, PlayerSpec
from game.session.models import GameLifecycle
from game.session.timer import TimerConfig
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockConnection, MockGameService
from game.wire.events import EVENT_TYPE_INT
from shared.dal.models import GameEndReason

from .helpers import game_of, runtime_of, wait_for_background_tasks

SHORT_PENDING_TIMEOUT = TimerConfig(pending_game_timeout_seconds=0.01, game_start_pause_seconds=0)
SHORT_START_PAUSE = TimerConfig(game_start_pause_seconds=0.01)
GAME_STARTED_T = EVENT_TYPE_INT[EventType.GAME_STARTED]
ROUND_STARTED_T = EVENT_TYPE_INT[EventType.ROUND_STARTED]


def _make_specs(count: int = 1) -> list[PlayerSpec]:
    return [
        PlayerSpec(
            name=f"Player{i}",
            user_id=f"user-{i}",
            game_ticket=f"ticket-{i}",
        )
        for i in range(count)
    ]


def _error_messages(conn: MockConnection) -> list[dict]:
    return [m for m in conn.sent_messages if m.get("type") == "session_error"]


def _error_codes(conn: MockConnection) -> list[str]:
    return [m["code"] for m in _error_messages(conn)]


def _join(manager, ticket: str, game_id: str = "game1") -> MockConnection:
    conn = MockConnection(game_id=game_id)
    manager.register_connection(conn)
    manager.join_game(conn, session_token=ticket)
    return conn


class TestCreatePendingGame:
    async def test_create_pending_game__when_created__should_register_a_pending_game_with_its_participants(
        self, manager
    ):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))
        game = game_of(manager)
        assert game.lifecycle is GameLifecycle.PENDING
        assert manager.pending_game_count == 1
        assert [participant.name for participant in game.participants] == ["Player0"]
        assert manager._participants_by_ticket["ticket-0"] is game.participants[0]

    async def test_create_pending_game__when_game_id_exists__should_raise_value_error(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))

        with pytest.raises(ValueError, match="already exists"):
            manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))


class TestJoinGame:
    async def test_join_game__when_ticket_unknown__should_return_no_session_error(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))

        conn = _join(manager, "invalid-ticket")
        assert _error_codes(conn) == [SessionErrorCode.JOIN_GAME_NO_SESSION]

    async def test_join_game__when_game_does_not_exist__should_return_not_found_error(self, manager):
        conn = _join(manager, "ticket-0", game_id="nonexistent")
        assert _error_codes(conn) == [SessionErrorCode.JOIN_GAME_NOT_FOUND]

    async def test_join_game__when_game_already_started__should_return_already_started_error(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))
        _join(manager, "ticket-0")
        assert game_of(manager).lifecycle is GameLifecycle.PLAYING

        conn2 = _join(manager, "ticket-0")
        assert _error_codes(conn2) == [SessionErrorCode.JOIN_GAME_ALREADY_STARTED]

    async def test_join_game__when_connection_already_joined__should_return_already_in_game_error(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        conn = _join(manager, "ticket-0")

        manager.join_game(conn, session_token="ticket-1")
        assert _error_codes(conn) == [SessionErrorCode.ALREADY_IN_GAME]

    async def test_join_game__when_ticket_belongs_to_other_game__should_return_game_mismatch_error(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))
        manager.create_pending_game(
            game_id="game2",
            player_specs=[PlayerSpec(name="OtherPlayer", user_id="other", game_ticket="other-ticket")],
        )

        conn = _join(manager, "ticket-0", game_id="game2")
        assert _error_codes(conn) == [SessionErrorCode.RECONNECT_GAME_MISMATCH]

    async def test_join_game__when_token_reused_by_new_connection__should_evict_and_close_the_old_connection(
        self, manager
    ):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        conn1 = _join(manager, "ticket-0")

        conn2 = _join(manager, "ticket-0")
        assert _error_messages(conn2) == []
        game = game_of(manager)
        assert game.lifecycle is GameLifecycle.PENDING
        assert [participant.connection for participant in game.connected()] == [conn2]
        assert conn1.connection_id not in manager._connections
        assert (conn1._close_code, conn1._close_reason) == (4002, "replaced_by_new_connection")

        manager.join_game(conn1, session_token="ticket-0")
        manager.disconnect(conn1)
        assert [participant.connection for participant in game.connected()] == [conn2]

    async def test_join_game__when_second_of_two_humans_joins__should_start_game(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        _join(manager, "ticket-0")
        assert game_of(manager).lifecycle is GameLifecycle.PENDING

        _join(manager, "ticket-1")
        assert game_of(manager).lifecycle is GameLifecycle.PLAYING
        assert manager.started_game_count == 1

    async def test_handle_game_action__when_game_still_pending__should_return_game_not_started_error(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        conn = _join(manager, "ticket-0")

        manager.handle_game_action(conn, action=GameAction.DISCARD, data={}, wait_id=0)
        assert _error_codes(conn) == [SessionErrorCode.GAME_NOT_STARTED]


class TestPendingGameTimeout:
    async def test_pending_game_timeout__when_a_human_never_connected__should_start_and_let_that_seat_reconnect(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine, timer_config=SHORT_PENDING_TIMEOUT)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        assert manager.get_playing_game_id("user-1") == "game1"
        conn = _join(manager, "ticket-0")
        game = game_of(manager)
        timeout_task = game.pending_timeout
        assert timeout_task is not None

        await timeout_task
        assert manager.get_playing_game_id("user-1") == "game1"
        game_started = [m for m in conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.GAME_STARTED]]
        assert len(game_started) == 1
        connected, absent = game.participants
        assert absent.seat is not None
        assert absent.seat != connected.seat
        assert not absent.is_connected
        snapshot = seeded_engine.build_reconnection_snapshot(runtime_of(manager), connected.seat)
        assert snapshot.players[absent.seat].is_ai_player is True

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, session_token="ticket-1")
        reconnected = [m for m in reconnecting.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert [m["s"] for m in reconnected] == [absent.seat]

        await manager.shutdown()

    async def test_pending_game_timeout__when_all_players_connect__should_cancel_timeout_task(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))
        timeout_task = game_of(manager).pending_timeout
        assert timeout_task is not None

        _join(manager, "ticket-0")
        with pytest.raises(asyncio.CancelledError):
            await timeout_task

    async def test_pending_game_timeout__when_no_players_connected__should_abandon_the_game_and_its_tickets(self):
        manager = make_session_manager(timer_config=SHORT_PENDING_TIMEOUT)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))
        game = game_of(manager)
        timeout_task = game.pending_timeout
        assert timeout_task is not None

        await timeout_task
        assert manager.get_game("game1") is None
        assert game.lifecycle in (GameLifecycle.ENDING, GameLifecycle.CLOSED)
        assert "ticket-0" not in manager._participants_by_ticket
        assert manager._game_repository.finishes == []


class TestGameStartPause:
    async def test_game_start_pause__when_every_player_joined__should_show_each_seat_the_start_then_deal_after_it(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine, timer_config=SHORT_START_PAUSE)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        conns = [_join(manager, "ticket-0"), _join(manager, "ticket-1")]
        game = game_of(manager)
        seats = [participant.seat for participant in game.participants]
        assert [[m["t"] for m in conn.sent_messages] for conn in conns] == [[GAME_STARTED_T], [GAME_STARTED_T]]
        assert [conn.sent_messages[0]["s"] for conn in conns] == seats
        assert [conn.sent_messages[0]["tm"] for conn in conns] == [{"tb": 5, "bk": 20, "rb": 10, "mb": 60, "md": 5}] * 2
        assert game.awaiting is None
        assert [participant.timer.task for participant in game.participants] == [None, None]
        assert game.start_pause is not None

        await game.start_pause
        assert [[m["t"] for m in conn.sent_messages][:2] for conn in conns] == [[GAME_STARTED_T, ROUND_STARTED_T]] * 2
        assert game.awaiting is not None
        awaited = [participant for participant in game.participants if participant.seat in game.awaiting.seats]
        assert awaited
        assert all(participant.timer.task is not None for participant in awaited)

        await manager.shutdown()

    async def test_game_start_pause__when_a_player_leaves_during_it__should_seat_an_ai_player_only_with_the_deal(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine, timer_config=SHORT_START_PAUSE)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")
        game = game_of(manager)
        bob_seat = game.participants[1].seat
        assert game.start_pause is not None

        manager.disconnect(bob)
        early_reconnect = MockConnection()
        manager.register_connection(early_reconnect)
        manager.reconnect(early_reconnect, session_token="ticket-1")
        assert _error_codes(early_reconnect) == [SessionErrorCode.RECONNECT_RETRY_LATER]
        assert runtime_of(manager).ai.is_ai_player(bob_seat) is False
        assert [m.get("t", m.get("type")) for m in alice.sent_messages] == [
            GAME_STARTED_T,
            SessionMessageType.PLAYER_LEFT,
        ]

        await game.start_pause
        assert alice.sent_messages[2]["t"] == ROUND_STARTED_T
        assert runtime_of(manager).ai.is_ai_player(bob_seat) is True

        manager.reconnect(early_reconnect, session_token="ticket-1")
        reconnected = [m for m in early_reconnect.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert [m["s"] for m in reconnected] == [bob_seat]

        await manager.shutdown()

    async def test_game_start_pause__when_every_player_leaves_during_it__should_abandon_the_game_without_a_deal(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine, timer_config=SHORT_START_PAUSE)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")
        game = game_of(manager)
        start_pause = game.start_pause
        assert start_pause is not None

        manager.disconnect(bob)
        manager.disconnect(alice)
        assert manager.get_game("game1") is None
        assert game.start_pause is None
        with pytest.raises(asyncio.CancelledError):
            await start_pause

        await wait_for_background_tasks(manager)
        assert [finish.end_reason for finish in manager._game_repository.finishes] == [GameEndReason.ABANDONED]
        assert [m.get("t") for m in alice.sent_messages if "t" in m] == [GAME_STARTED_T]

    async def test_game_start_pause__when_the_deal_raises__should_fail_the_game(self):
        game_service = MockGameService()
        game_service.replace_with_ai_player = MagicMock(side_effect=RuntimeError("replace failed"))
        manager = make_session_manager(game_service, timer_config=SHORT_START_PAUSE)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")
        start_pause = game_of(manager).start_pause
        assert start_pause is not None

        manager.disconnect(bob)
        await start_pause
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert _error_codes(alice) == [SessionErrorCode.INTERNAL_ERROR]
        assert alice._close_code == 1011


class TestPendingGameDisconnect:
    async def test_pending_game_disconnect__when_player_leaves__should_keep_the_game_pending_for_a_rejoin(
        self, manager
    ):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        conn1 = _join(manager, "ticket-0")

        manager.disconnect(conn1)
        game = game_of(manager)
        assert game.lifecycle is GameLifecycle.PENDING
        assert game.connected() == []

        conn2 = _join(manager, "ticket-0")
        assert _error_messages(conn2) == []
        assert [participant.connection for participant in game.connected()] == [conn2]


class TestCreateGameRequestValidation:
    def test_create_game_request__when_player_count_mismatches_ai_count__should_raise_value_error(self):
        with pytest.raises(ValueError, match="Expected 1 players"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=3,
                players=[
                    PlayerSpec(name="Alice", user_id="u1", game_ticket="t1"),
                    PlayerSpec(name="Bob", user_id="u2", game_ticket="t2"),
                ],
            )

    def test_create_game_request__when_game_tickets_duplicate__should_raise_value_error(self):
        with pytest.raises(ValueError, match="Duplicate game_ticket"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=2,
                players=[
                    PlayerSpec(name="Alice", user_id="u1", game_ticket="same-ticket"),
                    PlayerSpec(name="Bob", user_id="u2", game_ticket="same-ticket"),
                ],
            )

    def test_create_game_request__when_player_names_duplicate__should_raise_value_error(self):
        with pytest.raises(ValueError, match="Duplicate player name"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=2,
                players=[
                    PlayerSpec(name="Alice", user_id="u1", game_ticket="t1"),
                    PlayerSpec(name="Alice", user_id="u2", game_ticket="t2"),
                ],
            )

    def test_create_game_request__when_user_ids_duplicate__should_raise_value_error(self):
        with pytest.raises(ValueError, match="Duplicate user_id"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=2,
                players=[
                    PlayerSpec(name="Alice", user_id="same-id", game_ticket="t1"),
                    PlayerSpec(name="Bob", user_id="same-id", game_ticket="t2"),
                ],
            )


class TestPostGamesEndpoint:
    @pytest.fixture
    def client(self):
        session_manager = make_session_manager()
        app = create_app(game_service=session_manager._game_service, session_manager=session_manager)
        with TestClient(app) as client:
            yield client

    @staticmethod
    def _signed_player(name: str, user_id: str, game_id: str) -> dict:
        ticket = make_test_game_ticket(username=name, room_id=game_id, user_id=user_id)
        return {"name": name, "user_id": user_id, "game_ticket": ticket}

    def test_post_games__when_body_valid__should_return_201_pending(self, client):
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [self._signed_player(name="Alice", user_id="u1", game_id="test-game")],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["game_id"] == "test-game"
        assert data["status"] == "pending"

    def test_post_games__when_body_not_json__should_return_400(self, client):
        response = client.post("/games", content=b"not json")
        assert response.status_code == 400

    def test_post_games__when_game_id_exists__should_return_409(self, client):
        # Create game first via endpoint
        client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [self._signed_player(name="Alice", user_id="u1", game_id="test-game")],
            },
        )

        # Duplicate
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [self._signed_player(name="Bob", user_id="u2", game_id="test-game")],
            },
        )
        assert response.status_code == 409

    def test_post_games__when_server_at_capacity__should_return_503(self, client):
        client.app.state.settings.max_capacity = 1

        response = client.post(
            "/games",
            json={
                "game_id": "game1",
                "num_ai_players": 3,
                "players": [self._signed_player(name="Alice", user_id="u1", game_id="game1")],
            },
        )
        assert response.status_code == 201

        response = client.post(
            "/games",
            json={
                "game_id": "game2",
                "num_ai_players": 3,
                "players": [self._signed_player(name="Bob", user_id="u2", game_id="game2")],
            },
        )
        assert response.status_code == 503

    def test_post_games__when_body_too_large__should_return_413(self, client):
        response = client.post("/games", content=b"x" * 5000)
        assert response.status_code == 413

    def test_post_games__when_ticket_invalid__should_return_400(self, client):
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [{"name": "Alice", "user_id": "u1", "game_ticket": "invalid-ticket"}],
            },
        )
        assert response.status_code == 400
        assert "Invalid or expired game ticket" in response.json()["error"]

    def test_post_games__when_ticket_game_id_differs__should_return_400(self, client):
        ticket = make_test_game_ticket(username="Alice", room_id="other-game", user_id="u1")

        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [{"name": "Alice", "user_id": "u1", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 400
        assert "game_id mismatch" in response.json()["error"]

    def test_post_games__when_ticket_identity_differs__should_return_400(self, client):
        ticket = make_test_game_ticket(username="Alice", room_id="test-game", user_id="u1")

        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [{"name": "FakeAlice", "user_id": "u1", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 400
        assert "identity mismatch" in response.json()["error"]


class TestJoinGameViaRouter:
    @pytest.fixture
    def router(self, manager):
        return MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)

    async def test_join_game_via_router__when_ticket_valid__should_start_game(self, manager, router):
        game_id = "test-game"
        ticket = make_test_game_ticket(username="Alice", room_id=game_id, user_id="alice-id")

        specs = [PlayerSpec(name="Alice", user_id="alice-id", game_ticket=ticket)]
        manager.create_pending_game(game_id=game_id, player_specs=specs)

        conn = MockConnection(game_id=game_id)
        router.handle_connect(conn)

        router.handle_message(
            conn,
            {
                "t": WireClientMessageType.JOIN_GAME,
                "game_ticket": ticket,
            },
        )
        assert game_of(manager, game_id).lifecycle is GameLifecycle.PLAYING

    async def test_join_game_via_router__when_ticket_forged__should_return_invalid_ticket_error(self, manager, router):
        game_id = "test-game"
        specs = [PlayerSpec(name="Alice", user_id="alice-id", game_ticket="valid-ticket")]
        manager.create_pending_game(game_id=game_id, player_specs=specs)

        conn = MockConnection(game_id=game_id)
        router.handle_connect(conn)

        router.handle_message(
            conn,
            {
                "t": WireClientMessageType.JOIN_GAME,
                "game_ticket": "forged-ticket",
            },
        )
        # Should get INVALID_TICKET error (signature verification fails)
        assert SessionErrorCode.INVALID_TICKET in _error_codes(conn)


class TestJoinGameViaWebSocket:
    @pytest.fixture
    def client(self):
        session_manager = make_session_manager()
        app = create_app(game_service=session_manager._game_service, session_manager=session_manager)
        with TestClient(app) as client:
            yield client

    def test_join_game_via_websocket__when_game_created_via_post__should_start_game_using_url_game_id(self, client):
        game_id = "ws-game"
        ticket = make_test_game_ticket(username="Alice", room_id=game_id, user_id="alice-id")

        # Create pending game via POST
        response = client.post(
            "/games",
            json={
                "game_id": game_id,
                "num_ai_players": 3,
                "players": [{"name": "Alice", "user_id": "alice-id", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 201

        # Connect via WebSocket and send JOIN_GAME (game_id from URL path)
        with client.websocket_connect(f"/ws/{game_id}") as ws:
            ws.send_bytes(
                encode(
                    {
                        "t": WireClientMessageType.JOIN_GAME,
                        "game_ticket": ticket,
                    },
                ),
            )

            # Should receive game events (game started)
            msg = decode(ws.receive_bytes())
            assert msg is not None
