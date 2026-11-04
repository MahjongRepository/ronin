from game.logic.events import EventType
from game.messaging.types import SessionErrorCode
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server import websocket as ws_module
from game.wire.compact import decode_discard
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey

from .helpers import runtime_of, start_over_sockets


class TestEndpointRateLimit:
    async def test_rate_limit__when_a_burst_refuses_an_old_action_after_the_game_advanced__should_name_its_wait(
        self, table, monkeypatch
    ):
        monkeypatch.setattr(ws_module, "_RATE_LIMIT_BURST", 2)
        monkeypatch.setattr(ws_module, "_RATE_LIMIT_RATE", 0.0)
        _, bob = await start_over_sockets(table)
        bob_seat = table.seat_of("Bob")
        table.advance_to_turn_of(bob_seat)
        previous = table.manager.get_game("game1").awaiting
        old_wait = table.manager.get_game("game1").at_seat(bob_seat).decision_id
        tile = runtime_of(table.manager).state.round_state.players[bob_seat].tiles[-1]
        old_discard = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.ACTION: WireGameAction.DISCARD,
            WireKey.TILE_ID: tile,
            WireKey.WAIT_ID: old_wait,
        }
        bob.send(old_discard)
        await bob.wait_for_message(
            lambda m: (
                m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.DISCARD]
                and decode_discard(m[WireKey.PACKED_MOVE])[:2] == (bob_seat, tile)
            )
        )
        assert table.manager.get_game("game1").awaiting != previous

        bob.send(old_discard)
        await bob.wait_for_message(lambda m: m.get(WireKey.SESSION_ERROR_CODE) == SessionErrorCode.RATE_LIMITED)
        assert bob.messages[-1] == {
            WireKey.SESSION_TYPE: "session_error",
            WireKey.SESSION_ERROR_CODE: "rate_limited",
            WireKey.SESSION_ERROR_MESSAGE: "Too many messages",
            WireKey.WAIT_ID: old_wait,
        }
