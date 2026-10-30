from game.logic.enums import TimeoutType
from game.logic.events import EventType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.tests.mocks import MockConnection
from game.wire.compact import decode_discard
from game.wire.events import EVENT_TYPE_INT
from shared import websocket as shared_websocket
from shared.dal.models import GameEndReason
from shared.tests.helpers.fake_websocket import ClosedWith

from .helpers import arrange_final_discard, run_timeout, runtime_of, start_over_sockets


class TestConnectionWriters:
    async def test_slow_reader__when_its_writes_are_held__should_not_delay_another_seats_action(self, table):
        alice, bob = await start_over_sockets(table)
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
        alice, bob = await start_over_sockets(table)
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
        bob = MockConnection()
        table.manager.register_connection(bob)
        table.manager.join_game(bob, session_token=table.tickets["Bob"])
        alice, alice_endpoint = table.join_over_socket("Alice", held=True)

        await alice_endpoint
        assert alice.written == []
        assert not table.manager._participants_by_ticket[table.tickets["Alice"]].is_connected
        snapshot = table.manager._game_service.build_reconnection_snapshot(
            runtime_of(table.manager), table.seat_of("Bob")
        )
        assert snapshot.players[table.seat_of("Alice")].is_ai_player is True
        assert {"type": "seat_control", "s": table.seat_of("Alice"), "r": 0} in bob.sent_messages
        await table.manager.shutdown()
