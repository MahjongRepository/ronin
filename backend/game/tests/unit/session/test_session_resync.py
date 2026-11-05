import asyncio

from game.messaging.types import SessionErrorCode, SessionMessageType
from game.messaging.wire_enums import WireClientMessageType
from game.server import websocket as ws_module
from game.server.websocket import websocket_endpoint
from game.session.models import PlayerSpec
from game.tests.helpers.fake_websocket import FakeWebSocketClient
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockConnection
from game.wire.keys import WireKey

from .helpers import create_started_game, game_of, participant_of, runtime_of, start_over_sockets

RESYNC = {WireKey.EVENT_TYPE: WireClientMessageType.RESYNC}


def _is_snapshot(message: dict) -> bool:
    return message.get(WireKey.SESSION_TYPE) == SessionMessageType.GAME_RECONNECTED


class TestResync:
    async def test_resync__when_the_turn_seat_asks__should_send_what_a_reconnect_sends_and_keep_the_seat_bound(
        self, seeded_engine, fake_clock
    ):
        manager = make_session_manager(seeded_engine, clock=fake_clock.monotonic)
        alice_conn, bob_conn = create_started_game(manager, player_names=["Alice", "Bob"])
        alice = participant_of(manager, alice_conn)
        runtime = runtime_of(manager)
        assert runtime.state.round_state.current_player_seat == alice.seat
        awaiting = game_of(manager).awaiting
        decision_id = alice.decision_id
        deadline, bank = alice.timer.task, alice.timer.bank_seconds
        replay_lines = list(game_of(manager).replay.records)
        fake_clock.advance(7)

        manager.resync(alice_conn)
        resynced = alice_conn.sent_messages
        assert [message.get(WireKey.SESSION_TYPE) for message in resynced] == [
            SessionMessageType.GAME_RECONNECTED,
            None,
        ]
        assert (resynced[1][WireKey.WAIT_ID], resynced[1][WireKey.WAIT_ELAPSED]) == (decision_id, 7)
        assert resynced[0][WireKey.TILES_REMAINING] == len(runtime.state.round_state.wall.live_tiles)
        assert WireKey.TILES_REMAINING not in resynced[1]
        assert alice.connection is alice_conn
        assert not alice_conn.is_closed
        assert alice.stand_in is None
        assert not runtime.ai.is_ai_player(alice.seat)
        assert game_of(manager).awaiting is awaiting
        assert alice.timer.task is deadline
        assert not deadline.done()
        assert alice.timer.bank_seconds == bank
        assert game_of(manager).replay.records == replay_lines
        assert bob_conn.sent_messages == []
        assert manager.stats["resyncs"] == 1

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token=alice.ticket)
        assert new_conn.sent_messages == resynced

        await manager.shutdown()

    async def test_resync__when_the_game_has_not_dealt__should_answer_game_not_started(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        specs = [PlayerSpec(name=name, user_id=f"user-{name}", game_ticket=f"ticket-{name}") for name in ("A", "B")]
        manager.create_pending_game(game_id="game1", player_specs=specs)
        conn = MockConnection()
        manager.register_connection(conn)
        manager.join_game(conn, session_token="ticket-A")
        conn._outbox.clear()

        manager.resync(conn)
        assert [message[WireKey.SESSION_ERROR_CODE] for message in conn.sent_messages] == [
            SessionErrorCode.GAME_NOT_STARTED
        ]

        await manager.shutdown()


class TestResyncEndpoint:
    async def test_resync_endpoint__when_over_its_budget__should_answer_rate_limited_naming_no_wait(
        self, table, monkeypatch
    ):
        monkeypatch.setattr(ws_module, "_RESYNC_RATE_LIMIT_BURST", 1)
        monkeypatch.setattr(ws_module, "_RESYNC_RATE_LIMIT_RATE", 0.0)
        _, bob = await start_over_sockets(table)

        bob.send(RESYNC)
        await bob.wait_for_message(_is_snapshot)
        bob.send(RESYNC)
        await bob.wait_for_message(lambda m: m.get(WireKey.SESSION_ERROR_CODE) == SessionErrorCode.RATE_LIMITED)
        assert bob.messages[-1] == {
            WireKey.SESSION_TYPE: "session_error",
            WireKey.SESSION_ERROR_CODE: "rate_limited",
            WireKey.SESSION_ERROR_MESSAGE: "Too many resync requests",
        }
        assert sum(1 for message in bob.messages if _is_snapshot(message)) == 1

    async def test_resync_endpoint__when_the_connection_joined_no_game__should_answer_not_in_game(self, table):
        stranger = FakeWebSocketClient()
        table.clients.append(stranger)
        table.endpoints.append(asyncio.create_task(websocket_endpoint(stranger.websocket, table.router)))

        stranger.send(RESYNC)
        await stranger.wait_for_message(lambda m: m.get(WireKey.SESSION_TYPE) == SessionMessageType.ERROR)
        assert [message[WireKey.SESSION_ERROR_CODE] for message in stranger.messages] == [SessionErrorCode.NOT_IN_GAME]
