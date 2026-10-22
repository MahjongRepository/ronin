import asyncio

import pytest

from game.logic.enums import TimeoutType, WaitKind
from game.logic.events import EventType
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server import websocket as ws_module
from game.server.router import MessageRouter
from game.server.websocket import websocket_endpoint
from game.session.manager import SessionManager
from game.session.models import PlayerSpec
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.helpers.fake_websocket import ClosedWith, FakeWebSocketClient
from game.tests.mocks import FakeGameRepository, MockConnection
from game.wire.compact import decode_discard
from game.wire.events import EVENT_TYPE_INT
from shared.dal.models import GameEndReason

from .helpers import arrange_final_discard, run_timeout

_TIMEOUT_OF_WAIT = {
    WaitKind.TURN: TimeoutType.TURN,
    WaitKind.CALL: TimeoutType.MELD,
    WaitKind.ROUND_ADVANCE: TimeoutType.ROUND_ADVANCE,
}


def _is_round_start(message: dict) -> bool:
    return message.get("t") == EVENT_TYPE_INT[EventType.ROUND_STARTED]


class _Table:
    def __init__(self, manager: SessionManager) -> None:
        self.manager = manager
        self.router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        self.tickets = {
            name: make_test_game_ticket(username=name, room_id="game1", user_id=f"user-{name}")
            for name in ("Alice", "Bob")
        }
        manager.create_pending_game(
            game_id="game1",
            player_specs=[
                PlayerSpec(name=name, user_id=f"user-{name}", game_ticket=ticket)
                for name, ticket in self.tickets.items()
            ],
        )
        self.clients: list[FakeWebSocketClient] = []
        self.endpoints: list[asyncio.Task[None]] = []

    def join_over_socket(self, name: str, *, held: bool = False) -> tuple[FakeWebSocketClient, asyncio.Task[None]]:
        client = FakeWebSocketClient()
        if held:
            client.hold_writes()

        endpoint = asyncio.create_task(websocket_endpoint(client.websocket, self.router))
        client.send({"t": WireClientMessageType.JOIN_GAME, "game_ticket": self.tickets[name]})
        self.clients.append(client)
        self.endpoints.append(endpoint)
        return client, endpoint

    def seat_of(self, name: str) -> int:
        session = self.manager._session_store.get_session(self.tickets[name])
        assert session is not None
        assert session.seat is not None
        return session.seat

    async def advance_to_turn_of(self, seat: int) -> None:
        game = self.manager.get_game("game1")
        while not (game.awaiting.kind == WaitKind.TURN and seat in game.awaiting.seats):
            waiting_seat = min(game.awaiting.seats)
            await run_timeout(
                self.manager, game_id="game1", timeout_type=_TIMEOUT_OF_WAIT[game.awaiting.kind], seat=waiting_seat
            )

    async def close(self) -> None:
        for client in self.clients:
            client.release_writes()
            client.disconnect()

        await asyncio.gather(*self.endpoints)
        await self.manager.shutdown()


@pytest.fixture
async def table(seeded_engine):
    table = _Table(SessionManager(seeded_engine, game_repository=FakeGameRepository()))
    yield table
    await table.close()


async def _start_over_sockets(table: _Table) -> tuple[FakeWebSocketClient, FakeWebSocketClient]:
    alice, _ = table.join_over_socket("Alice")
    bob, _ = table.join_over_socket("Bob")
    await alice.wait_for_message(_is_round_start)
    await bob.wait_for_message(_is_round_start)
    return alice, bob


class TestConnectionWriters:
    async def test_slow_reader__when_its_writes_are_held__should_not_delay_another_seats_action(
        self, table, seeded_engine
    ):
        alice, bob = await _start_over_sockets(table)
        bob_seat = table.seat_of("Bob")
        await table.advance_to_turn_of(bob_seat)
        alice.hold_writes()
        wait_id = table.manager.get_game("game1").awaiting.wait_id
        tile = seeded_engine.get_game_state("game1").round_state.players[bob_seat].tiles[-1]

        bob.send({"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": tile, "wi": wait_id})
        bob.send({"t": WireClientMessageType.CHAT, "text": "sent after the discard"})
        await bob.wait_for_message(lambda m: m.get("text") == "sent after the discard")
        assert table.manager.get_game("game1").awaiting.wait_id != wait_id
        assert any(
            m.get("t") == EVENT_TYPE_INT[EventType.DISCARD] and decode_discard(m["d"])[:2] == (bob_seat, tile)
            for m in bob.messages
        )

    async def test_game_end__when_one_reader_is_held__should_close_the_others_after_game_end_without_waiting(
        self, table, seeded_engine
    ):
        alice, bob = await _start_over_sockets(table)
        game = table.manager.get_game("game1")
        alice_seat = table.seat_of("Alice")
        await table.advance_to_turn_of(alice_seat)
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)
        alice.hold_writes()

        await run_timeout(table.manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        assert game.end_reason is GameEndReason.COMPLETED
        assert await bob.wait_for_close() == ClosedWith(code=1000, reason="game_ended")
        assert bob.messages[-1]["t"] == EVENT_TYPE_INT[EventType.GAME_END]

    async def test_send_queue_overflow__when_a_held_reader_overflows__should_seat_an_ai_player_through_the_disconnect(
        self, table, monkeypatch
    ):
        monkeypatch.setattr(ws_module, "_SEND_QUEUE_LIMIT", 2)
        bob = MockConnection(game_id="game1")
        table.manager.register_connection(bob)
        await table.manager.join_game(bob, game_id="game1", session_token=table.tickets["Bob"])
        alice, alice_endpoint = table.join_over_socket("Alice", held=True)
        for n in range(5):
            alice.send({"t": WireClientMessageType.CHAT, "text": f"post-overflow-{n}"})

        await alice_endpoint
        assert alice.written == []
        assert [m for m in bob.sent_messages if m.get("type") == SessionMessageType.CHAT] == []
        alice_session = table.manager._session_store.get_session(table.tickets["Alice"])
        assert alice_session.disconnected_at is not None
        snapshot = table.manager._game_service.build_reconnection_snapshot("game1", table.seat_of("Bob"))
        assert snapshot.players[table.seat_of("Alice")].is_ai_player is True
        assert {"type": SessionMessageType.PLAYER_LEFT, "player_name": "Alice"} in bob.sent_messages
        await table.manager.shutdown()
