import asyncio

import pytest
from starlette.testclient import TestClient

from game.logic.enums import GameAction, WaitKind
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
from game.tests.mocks import MockConnection
from game.wire.compact import decode_discard
from game.wire.enums import WireEventType
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey
from shared.dal.models import GameEndReason

from .helpers import game_of, runtime_of, wait_for_background_tasks

SHORT_PENDING_TIMEOUT = TimerConfig(
    pending_game_timeout_seconds=0.01, game_start_confirm_seconds=0, ai_turn_delay_seconds=0
)
START_CONFIRM_SECONDS = 10
START_CONFIRM = TimerConfig(game_start_confirm_seconds=START_CONFIRM_SECONDS, ai_turn_delay_seconds=0)
GAME_STARTED_T = EVENT_TYPE_INT[EventType.GAME_STARTED]
ROUND_STARTED_T = EVENT_TYPE_INT[EventType.ROUND_STARTED]
DRAW_T = EVENT_TYPE_INT[EventType.DRAW]
DISCARD_T = EVENT_TYPE_INT[EventType.DISCARD]


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
    return [m for m in conn.sent_messages if m.get(WireKey.SESSION_TYPE) == "session_error"]


def _error_codes(conn: MockConnection) -> list[str]:
    return [m[WireKey.SESSION_ERROR_CODE] for m in _error_messages(conn)]


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
        assert manager.stats["takeovers"] == 1

        manager.join_game(conn1, session_token="ticket-0")
        manager.disconnect(conn1)
        assert [participant.connection for participant in game.connected()] == [conn2]

    async def test_join_game__when_second_of_two_humans_joins__should_answer_each_join_first_and_start_game(
        self, manager
    ):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        first = _join(manager, "ticket-0")
        assert game_of(manager).lifecycle is GameLifecycle.PENDING
        joined = {
            WireKey.PENDING_GAME_TIMEOUT: game_of(manager).timer_config.pending_game_timeout_seconds,
            WireKey.SESSION_TYPE: SessionMessageType.GAME_JOINED,
        }
        assert first.sent_messages == [joined]

        second = _join(manager, "ticket-1")
        assert game_of(manager).lifecycle is GameLifecycle.PLAYING
        assert manager.started_game_count == 1
        assert second.sent_messages[0] == joined
        assert second.sent_messages[1][WireKey.EVENT_TYPE] == GAME_STARTED_T

    async def test_handle_game_action__when_game_still_pending__should_return_game_not_started_error(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        conn = _join(manager, "ticket-0")

        manager.handle_game_action(conn, action=GameAction.DISCARD, data={}, wait_id=0)
        assert _error_codes(conn) == [SessionErrorCode.GAME_NOT_STARTED]


class TestPendingGameTimeout:
    async def test_pending_game_timeout__when_dealer_never_connected__should_play_it_by_ai_and_let_it_reconnect(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine, timer_config=SHORT_PENDING_TIMEOUT)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        assert manager.get_playing_game_id("user-0") == "game1"
        conn = _join(manager, "ticket-1")
        game = game_of(manager)
        timeout_task = game.pending_timeout
        assert timeout_task is not None

        await timeout_task
        assert manager.get_playing_game_id("user-0") == "game1"
        game_started = [
            m for m in conn.sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.GAME_STARTED]
        ]
        assert len(game_started) == 1
        absent, connected = game.participants
        assert absent.seat == runtime_of(manager).state.round_state.dealer_seat
        assert absent.seat != connected.seat
        assert not absent.is_connected
        snapshot = seeded_engine.build_reconnection_snapshot(runtime_of(manager), connected.seat)
        assert snapshot.players[absent.seat].is_ai_player is True
        assert game.awaiting is not None
        assert game.awaiting.seats == {connected.seat}
        recorded = game.replay.records
        assert [line[WireKey.EVENT_TYPE] for line in recorded[:5]] == [
            GAME_STARTED_T,
            ROUND_STARTED_T,
            101,
            DRAW_T,
            DISCARD_T,
        ]
        assert recorded[2] == {
            WireKey.EVENT_TYPE: 101,
            WireKey.SEAT: absent.seat,
            WireKey.AI_PLAYER: 1,
            WireKey.SEAT_CONTROL_REASON: 1,
        }
        assert decode_discard(recorded[4][WireKey.PACKED_MOVE])[0] == absent.seat

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, session_token="ticket-0")
        reconnected = [
            m for m in reconnecting.sent_messages if m.get(WireKey.SESSION_TYPE) == SessionMessageType.GAME_RECONNECTED
        ]
        assert [m[WireKey.SEAT] for m in reconnected] == [absent.seat]

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


class TestWithdrawGame:
    async def test_withdraw_game__when_nobody_joined__should_abandon_it_and_free_its_players(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        game = game_of(manager)

        assert manager.withdraw_game("game1") is True
        assert manager.get_game("game1") is None
        assert game.lifecycle in (GameLifecycle.ENDING, GameLifecycle.CLOSED)
        assert manager.get_playing_game_id("user-0") is None
        assert manager.get_playing_game_id("user-1") is None
        await wait_for_background_tasks(manager)
        assert manager._game_repository.finishes == []

    async def test_withdraw_game__when_creation_arrives_after_it__should_refuse_the_creation(self, manager):
        assert manager.withdraw_game("game1") is True

        with pytest.raises(ValueError, match="withdrawn"):
            manager.create_pending_game(game_id="game1", player_specs=_make_specs(1))
        assert manager.get_playing_game_id("user-0") is None

    async def test_withdraw_game__when_a_player_joined__should_keep_the_game(self, manager):
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        _join(manager, "ticket-0")

        assert manager.withdraw_game("game1") is False
        assert game_of(manager).lifecycle is GameLifecycle.PENDING
        assert manager.get_playing_game_id("user-1") == "game1"


class TestGameStartConfirm:
    async def test_game_start_confirm__when_every_player_confirms__should_draw_at_once(self, seeded_engine, held_sleep):
        manager = make_session_manager(seeded_engine, timer_config=START_CONFIRM)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")
        game = game_of(manager)
        alice_participant, bob_participant = game.participants
        seats = [alice_participant.seat, bob_participant.seat]
        assert [[m.get(WireKey.EVENT_TYPE) for m in conn.sent_messages] for conn in (alice, bob)] == [
            [None, GAME_STARTED_T, ROUND_STARTED_T]
        ] * 2
        assert [conn.sent_messages[1][WireKey.TIMER_SETTINGS] for conn in (alice, bob)] == [
            {
                WireKey.BASE_TURN_SECONDS: 10,
                WireKey.BANK_SECONDS: 20,
                WireKey.MAX_BANK_SECONDS: 20,
                WireKey.ROUND_ADVANCE_TIMEOUT: 15,
                WireKey.GAME_START_CONFIRM: START_CONFIRM_SECONDS,
            }
        ] * 2
        assert [
            (conn.sent_messages[2][WireKey.WAIT_ID], conn.sent_messages[2][WireKey.ROUND_ADVANCE_SECONDS])
            for conn in (alice, bob)
        ] == [(1, START_CONFIRM_SECONDS)] * 2
        assert (game.awaiting.kind, game.awaiting.starts_game, game.awaiting.seats) == (
            WaitKind.ROUND_ADVANCE,
            True,
            frozenset(seats),
        )
        await asyncio.sleep(0)
        assert held_sleep.durations == [START_CONFIRM_SECONDS] * 2

        manager.handle_game_action(alice, action=GameAction.CONFIRM_ROUND, data={}, wait_id=1)
        assert [len(conn.sent_messages) for conn in (alice, bob)] == [3, 3]
        assert game.awaiting.seats == {bob_participant.seat}
        assert alice_participant.timer.task is None

        manager.handle_game_action(bob, action=GameAction.CONFIRM_ROUND, data={}, wait_id=1)
        dealer_seat = runtime_of(manager).state.round_state.dealer_seat
        assert [conn.sent_messages[3][WireKey.EVENT_TYPE] for conn in (alice, bob)] == [
            DRAW_T if seat == dealer_seat else WireEventType.DRAW_NOTICE for seat in seats
        ]
        assert game.awaiting.kind in (WaitKind.TURN, WaitKind.CALL)

        await manager.shutdown()

    async def test_game_start_confirm__when_its_timeout_fires__should_confirm_for_the_seats_left_and_draw(
        self, seeded_engine, held_sleep
    ):
        manager = make_session_manager(seeded_engine, timer_config=START_CONFIRM)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")
        game = game_of(manager)
        manager.handle_game_action(alice, action=GameAction.CONFIRM_ROUND, data={}, wait_id=1)
        await asyncio.sleep(0)

        await held_sleep.release_all()
        assert manager.stats["timeouts_round_advance"] == 1
        assert [
            conn.sent_messages[3][WireKey.EVENT_TYPE] in (DRAW_T, WireEventType.DRAW_NOTICE) for conn in (alice, bob)
        ] == [
            True,
            True,
        ]
        assert game.awaiting.kind is not WaitKind.ROUND_ADVANCE

        await manager.shutdown()

    async def test_game_start_confirm__when_a_player_leaves_during_it__should_stop_awaiting_the_seat(
        self, seeded_engine, held_sleep
    ):
        manager = make_session_manager(seeded_engine, timer_config=START_CONFIRM)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")
        game = game_of(manager)
        alice_seat, bob_seat = (participant.seat for participant in game.participants)

        manager.disconnect(bob)
        assert alice.sent_messages[3] == {
            WireKey.SESSION_TYPE: "seat_control",
            WireKey.SEAT: bob_seat,
            WireKey.SEAT_CONTROL_REASON: 0,
        }
        assert game.awaiting.seats == {alice_seat}

        bob_again = MockConnection()
        manager.register_connection(bob_again)
        manager.reconnect(bob_again, session_token="ticket-1")
        reconnected = bob_again.sent_messages[0]
        assert reconnected[WireKey.SESSION_TYPE] == SessionMessageType.GAME_RECONNECTED
        assert reconnected[WireKey.CONFIRMATION_OWED] is False
        assert WireKey.ROUND_ADVANCE_SECONDS not in reconnected
        assert game.awaiting.seats == {alice_seat}

        manager.handle_game_action(alice, action=GameAction.CONFIRM_ROUND, data={}, wait_id=1)
        recorded = game.replay.records
        assert [line[WireKey.EVENT_TYPE] for line in recorded[:5]] == [
            GAME_STARTED_T,
            ROUND_STARTED_T,
            101,
            101,
            DRAW_T,
        ]

        await manager.shutdown()

    async def test_game_start_confirm__when_a_seat_reconnects_over_its_socket__should_owe_the_confirmation(
        self, seeded_engine, held_sleep, fake_clock
    ):
        manager = make_session_manager(seeded_engine, timer_config=START_CONFIRM, clock=fake_clock.monotonic)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, _bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")
        fake_clock.advance(2)

        alice_again = MockConnection()
        manager.register_connection(alice_again)
        manager.reconnect(alice_again, session_token="ticket-0")
        assert alice._close_code == 4002
        assert [message.get(WireKey.SESSION_TYPE) for message in alice_again.sent_messages] == [
            SessionMessageType.GAME_RECONNECTED
        ]
        snapshot = alice_again.sent_messages[0]
        assert (
            snapshot[WireKey.WAIT_ID],
            snapshot[WireKey.CONFIRMATION_OWED],
            snapshot[WireKey.WAIT_ELAPSED],
            snapshot[WireKey.ROUND_ADVANCE_SECONDS],
        ) == (1, True, 2, START_CONFIRM_SECONDS)
        assert WireKey.ROUND_RESULT not in snapshot

        manager.handle_game_action(alice_again, action=GameAction.CONFIRM_ROUND, data={}, wait_id=1)
        assert game_of(manager).awaiting.seats == {game_of(manager).participants[1].seat}

        await manager.shutdown()

    async def test_game_start_confirm__when_every_player_leaves_during_it__should_abandon_the_game_before_the_draw(
        self, seeded_engine, held_sleep
    ):
        manager = make_session_manager(seeded_engine, timer_config=START_CONFIRM)
        manager.create_pending_game(game_id="game1", player_specs=_make_specs(2))
        alice, bob = _join(manager, "ticket-0"), _join(manager, "ticket-1")

        manager.disconnect(bob)
        manager.disconnect(alice)
        assert manager.get_game("game1") is None

        await wait_for_background_tasks(manager)
        assert [finish.end_reason for finish in manager._game_repository.finishes] == [GameEndReason.ABANDONED]
        assert [m.get(WireKey.EVENT_TYPE) for m in alice.sent_messages if WireKey.EVENT_TYPE in m] == [
            GAME_STARTED_T,
            ROUND_STARTED_T,
        ]


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

    def test_delete_game__when_caller_has_the_internal_secret__should_withdraw_the_pending_game(self, client):
        body = {
            "game_id": "test-game",
            "num_ai_players": 3,
            "players": [self._signed_player(name="Alice", user_id="u1", game_id="test-game")],
        }
        client.post("/games", json=body)
        secret = client.app.state.settings.internal_api_secret

        response = client.delete("/games/test-game", headers={"Authorization": f"Bearer {secret}"})
        assert response.status_code == 204
        assert client.get("/players/u1").status_code == 404
        assert client.post("/games", json=body).status_code == 409

    def test_delete_game__when_caller_lacks_the_internal_secret__should_answer_401_and_keep_the_game(self, client):
        client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [self._signed_player(name="Alice", user_id="u1", game_id="test-game")],
            },
        )

        response = client.delete("/games/test-game", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401
        assert client.get("/players/u1").json() == {"game_id": "test-game"}


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
                WireKey.EVENT_TYPE: WireClientMessageType.JOIN_GAME,
                WireKey.GAME_TICKET: ticket,
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
                WireKey.EVENT_TYPE: WireClientMessageType.JOIN_GAME,
                WireKey.GAME_TICKET: "forged-ticket",
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
                        WireKey.EVENT_TYPE: WireClientMessageType.JOIN_GAME,
                        WireKey.GAME_TICKET: ticket,
                    },
                ),
            )

            # Should receive game events (game started)
            msg = decode(ws.receive_bytes())
            assert msg is not None
