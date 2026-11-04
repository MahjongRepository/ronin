from game.logic.enums import GameAction, WaitKind
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.wire.enums import WireEventType

from .helpers import create_started_game, game_of, participant_of, runtime_of


async def test_decision_ids__when_opponents_pass_private_calls__should_hide_their_waits(seeded_engine, fake_clock):
    manager = make_session_manager(seeded_engine, clock=fake_clock.monotonic)
    alice, _, caller, idle = create_started_game(
        manager, player_names=["Alice", "Bob", "Carol", "Dave"], keep_start_messages=True
    )
    runtime = runtime_of(manager)
    alice_seat, caller_seat = participant_of(manager, alice).seat, participant_of(manager, caller).seat
    draw = next(message for message in alice.sent_messages if message.get("t") == WireEventType.DRAW)
    assert draw["wi"] == 1
    assert game_of(manager).awaiting.seats == frozenset({alice_seat})
    tile = runtime.state.round_state.players[alice_seat].tiles[-1]

    manager.handle_game_action(alice, action=GameAction.DISCARD, data={"tile_id": tile}, wait_id=draw["wi"])
    assert game_of(manager).awaiting.kind == WaitKind.CALL
    assert game_of(manager).awaiting.seats == frozenset({caller_seat})
    prompt = next(message for message in caller.sent_messages if message.get("t") == WireEventType.CALL_PROMPT)
    assert prompt["wi"] == 1

    alice._outbox.clear()
    manager.resync(alice)
    assert len(alice.sent_messages) == 1
    assert (alice.sent_messages[0]["type"], alice.sent_messages[0]["wi"]) == (
        SessionMessageType.GAME_RECONNECTED,
        1,
    )

    manager.handle_game_action(caller, action=GameAction.PASS, data={}, wait_id=prompt["wi"])
    assert game_of(manager).awaiting.kind == WaitKind.TURN
    next_draw = next(message for message in caller.sent_messages if message.get("t") == WireEventType.DRAW)
    assert next_draw["wi"] == 2

    alice._outbox.clear()
    manager.resync(alice)
    assert len(alice.sent_messages) == 1
    assert alice.sent_messages[0]["wi"] == 1
    idle._outbox.clear()
    manager.resync(idle)
    assert len(idle.sent_messages) == 1
    assert idle.sent_messages[0]["wi"] == 0

    alice._outbox.clear()
    router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
    state_before, awaiting_before = runtime.state, game_of(manager).awaiting
    deadline = participant_of(manager, caller).timer.task
    guesses = (draw["wi"], next_draw["wi"], awaiting_before.wait_id)
    for guess in guesses:
        router.handle_message(alice, {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.PASS, "wi": guess})

    assert alice.sent_messages == [
        {
            "t": WireEventType.ERROR,
            "cd": "stale_action",
            "msg": "the wait this action answers has already ended",
            "wi": guess,
        }
        for guess in guesses
    ]
    assert runtime.state is state_before
    assert game_of(manager).awaiting is awaiting_before
    assert participant_of(manager, caller).timer.task is deadline

    await manager.shutdown()
