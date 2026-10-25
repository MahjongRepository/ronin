import asyncio
from typing import TYPE_CHECKING

import pytest

from game.logic.enums import TimeoutType, WaitKind
from game.logic.events import EventType
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.server.websocket import websocket_endpoint
from game.session.models import PlayerSpec
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.helpers.fake_websocket import FakeWebSocketClient
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockConnection
from game.wire.compact import decode_discard
from game.wire.events import EVENT_TYPE_INT
from shared import websocket as shared_websocket
from shared.dal.models import GameEndReason
from shared.tests.helpers.fake_websocket import ClosedWith

from .helpers import arrange_final_discard, run_timeout, runtime_of

if TYPE_CHECKING:
    from game.session.manager import SessionManager

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
        seat = self.manager._participants_by_ticket[self.tickets[name]].seat
        assert seat is not None
        return seat

    def advance_to_turn_of(self, seat: int) -> None:
        game = self.manager.get_game("game1")
        while not (game.awaiting.kind == WaitKind.TURN and seat in game.awaiting.seats):
            waiting_seat = min(game.awaiting.seats)
            run_timeout(
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
    table = _Table(make_session_manager(seeded_engine))
    yield table
    await table.close()


async def _start_over_sockets(table: _Table) -> tuple[FakeWebSocketClient, FakeWebSocketClient]:
    alice, _ = table.join_over_socket("Alice")
    bob, _ = table.join_over_socket("Bob")
    await alice.wait_for_message(_is_round_start)
    await bob.wait_for_message(_is_round_start)
    return alice, bob


class TestConnectionWriters:
    async def test_slow_reader__when_its_writes_are_held__should_not_delay_another_seats_action(self, table):
        alice, bob = await _start_over_sockets(table)
        bob_seat = table.seat_of("Bob")
        table.advance_to_turn_of(bob_seat)
        alice.hold_writes()
        wait_id = table.manager.get_game("game1").awaiting.wait_id
        tile = runtime_of(table.manager).state.round_state.players[bob_seat].tiles[-1]

        bob.send({"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": tile, "wi": wait_id})
        await bob.wait_for_message(
            lambda m: m.get("t") == EVENT_TYPE_INT[EventType.DISCARD] and decode_discard(m["d"])[:2] == (bob_seat, tile)
        )
        assert table.manager.get_game("game1").awaiting.wait_id != wait_id

    async def test_game_end__when_one_reader_is_held__should_close_the_others_after_game_end_without_waiting(
        self, table
    ):
        alice, bob = await _start_over_sockets(table)
        alice_seat = table.seat_of("Alice")
        table.advance_to_turn_of(alice_seat)
        arrange_final_discard(runtime_of(table.manager), seat=alice_seat)
        alice.hold_writes()

        run_timeout(table.manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        assert await bob.wait_for_close() == ClosedWith(code=1000, reason="game_ended")
        assert bob.messages[-1]["t"] == EVENT_TYPE_INT[EventType.GAME_END]
        assert table.manager._game_repository.games["game1"].end_reason is GameEndReason.COMPLETED

    async def test_send_queue_overflow__when_a_held_reader_overflows__should_seat_an_ai_player_through_the_disconnect(
        self, table, monkeypatch
    ):
        monkeypatch.setattr(shared_websocket, "_SEND_QUEUE_LIMIT", 2)
        bob = MockConnection(game_id="game1")
        table.manager.register_connection(bob)
        table.manager.join_game(bob, game_id="game1", session_token=table.tickets["Bob"])
        alice, alice_endpoint = table.join_over_socket("Alice", held=True)

        await alice_endpoint
        assert alice.written == []
        assert not table.manager._participants_by_ticket[table.tickets["Alice"]].is_connected
        snapshot = table.manager._game_service.build_reconnection_snapshot(
            runtime_of(table.manager), table.seat_of("Bob")
        )
        assert snapshot.players[table.seat_of("Alice")].is_ai_player is True
        assert {"type": SessionMessageType.PLAYER_LEFT, "player_name": "Alice"} in bob.sent_messages
        await table.manager.shutdown()
