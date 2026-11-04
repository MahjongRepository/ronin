from game.logic.enums import GameAction, WaitKind
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.wire.enums import WireEventType
from game.wire.keys import WireKey

from .helpers import create_started_game, game_of, participant_of, runtime_of


async def test_decision_ids__when_opponents_pass_private_calls__should_hide_their_waits(seeded_engine, fake_clock):
    manager = make_session_manager(seeded_engine, clock=fake_clock.monotonic)
    alice, _, caller, idle = create_started_game(
        manager, player_names=["Alice", "Bob", "Carol", "Dave"], keep_start_messages=True
    )
    runtime = runtime_of(manager)
    alice_seat, caller_seat = participant_of(manager, alice).seat, participant_of(manager, caller).seat
    draw = next(message for message in alice.sent_messages if message.get(WireKey.EVENT_TYPE) == WireEventType.DRAW)
    assert draw[WireKey.WAIT_ID] == 1
    assert game_of(manager).awaiting.seats == frozenset({alice_seat})
    tile = runtime.state.round_state.players[alice_seat].tiles[-1]

    manager.handle_game_action(alice, action=GameAction.DISCARD, data={"tile_id": tile}, wait_id=draw[WireKey.WAIT_ID])
    assert game_of(manager).awaiting.kind == WaitKind.CALL
    assert game_of(manager).awaiting.seats == frozenset({caller_seat})
    prompt = next(
        message for message in caller.sent_messages if message.get(WireKey.EVENT_TYPE) == WireEventType.CALL_PROMPT
    )
    assert prompt[WireKey.WAIT_ID] == 1

    alice._outbox.clear()
    manager.resync(alice)
    assert len(alice.sent_messages) == 1
    assert (alice.sent_messages[0][WireKey.SESSION_TYPE], alice.sent_messages[0][WireKey.WAIT_ID]) == (
        SessionMessageType.GAME_RECONNECTED,
        1,
    )

    manager.handle_game_action(caller, action=GameAction.PASS, data={}, wait_id=prompt[WireKey.WAIT_ID])
    assert game_of(manager).awaiting.kind == WaitKind.TURN
    next_draw = next(
        message for message in caller.sent_messages if message.get(WireKey.EVENT_TYPE) == WireEventType.DRAW
    )
    assert next_draw[WireKey.WAIT_ID] == 2

    alice._outbox.clear()
    manager.resync(alice)
    assert len(alice.sent_messages) == 1
    assert alice.sent_messages[0][WireKey.WAIT_ID] == 1
    idle._outbox.clear()
    manager.resync(idle)
    assert len(idle.sent_messages) == 1
    assert idle.sent_messages[0][WireKey.WAIT_ID] == 0

    alice._outbox.clear()
    router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
    state_before, awaiting_before = runtime.state, game_of(manager).awaiting
    deadline = participant_of(manager, caller).timer.task
    guesses = (draw[WireKey.WAIT_ID], next_draw[WireKey.WAIT_ID], awaiting_before.wait_id)
    for guess in guesses:
        router.handle_message(
            alice,
            {
                WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
                WireKey.ACTION: WireGameAction.PASS,
                WireKey.WAIT_ID: guess,
            },
        )

    assert alice.sent_messages == [
        {
            WireKey.EVENT_TYPE: WireEventType.ERROR,
            WireKey.GAME_ERROR_CODE: "stale_action",
            WireKey.GAME_ERROR_MESSAGE: "the wait this action answers has already ended",
            WireKey.WAIT_ID: guess,
        }
        for guess in guesses
    ]
    assert runtime.state is state_before
    assert game_of(manager).awaiting is awaiting_before
    assert participant_of(manager, caller).timer.task is deadline

    await manager.shutdown()
