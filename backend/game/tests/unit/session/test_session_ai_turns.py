import asyncio
from typing import TYPE_CHECKING

from game.logic import mahjong_service as mahjong_service_module
from game.logic.enums import GameAction, WaitKind
from game.logic.events import EventType
from game.session.timer import TimerConfig
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockConnection
from game.wire.compact import decode_discard
from game.wire.enums import WireEventType
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey
from shared.dal.models import GameEndReason

from .helpers import create_started_game, game_of, participant_of, runtime_of, wait_for_background_tasks

if TYPE_CHECKING:
    from game.session.manager import SessionManager

    from .conftest import HeldSleep

AI_TURN_DELAY = 0.5
START_CONFIRM = 2.0
PACED_AI_TURNS = TimerConfig(game_start_confirm_seconds=0, ai_turn_delay_seconds=AI_TURN_DELAY)
AI_DEALER_SEED = "c" * 192
DISCARD_T = EVENT_TYPE_INT[EventType.DISCARD]
DRAW_T = EVENT_TYPE_INT[EventType.DRAW]


def _take_discarders(conn: MockConnection) -> list[int]:
    seats = [
        decode_discard(message[WireKey.PACKED_MOVE])[0]
        for message in conn.sent_messages
        if message.get(WireKey.EVENT_TYPE) == DISCARD_T
    ]
    conn._outbox.clear()
    return seats


async def _end_held_sleeps(held_sleep: HeldSleep) -> None:
    await asyncio.sleep(0)
    await held_sleep.release_all()


def _discard_drawn_tile(manager: SessionManager, conn: MockConnection) -> None:
    participant = participant_of(manager, conn)
    seat = participant.seat
    assert seat is not None
    tile_id = runtime_of(manager).state.round_state.players[seat].tiles[-1]
    manager.handle_game_action(
        conn, action=GameAction.DISCARD, data={"tile_id": tile_id}, wait_id=participant.decision_id
    )


async def test_ai_turn_delay__when_the_start_confirm_hands_the_turn_to_ai_players__should_send_one_turn_per_delay(
    seeded_engine, held_manager_sleep, monkeypatch
):
    monkeypatch.setattr(mahjong_service_module, "generate_seed", lambda: AI_DEALER_SEED)
    config = TimerConfig(game_start_confirm_seconds=START_CONFIRM, ai_turn_delay_seconds=AI_TURN_DELAY)
    manager = make_session_manager(seeded_engine, timer_config=config)
    [alice] = create_started_game(manager, player_names=["Alice"])
    game = game_of(manager)
    alice_seat = participant_of(manager, alice).seat
    dealer_seat = runtime_of(manager).state.round_state.dealer_seat
    assert dealer_seat != alice_seat

    manager.handle_game_action(
        alice, action=GameAction.CONFIRM_ROUND, data={}, wait_id=participant_of(manager, alice).decision_id
    )
    assert [m.get(WireKey.EVENT_TYPE) for m in alice.sent_messages][-1:] == [WireEventType.DRAW_NOTICE]
    assert (game.awaiting.kind, game.ai_turn is not None) == (WaitKind.AI_TURN, True)
    assert _take_discarders(alice) == []

    discarders_per_delay = []
    for _ in range(3):
        await _end_held_sleeps(held_manager_sleep)
        discarders_per_delay.append(_take_discarders(alice))

    assert discarders_per_delay == [[dealer_seat], [(dealer_seat + 1) % 4], [(dealer_seat + 2) % 4]]
    assert held_manager_sleep.durations.count(AI_TURN_DELAY) == 3
    assert (game.awaiting.kind, game.awaiting.seats, game.ai_turn) == (WaitKind.TURN, frozenset({alice_seat}), None)
    assert participant_of(manager, alice).timer.task is not None

    await manager.shutdown()


async def test_ai_turn_delay__when_a_human_leaves_during_it__should_keep_one_ai_turn_per_delay(
    seeded_engine, held_manager_sleep
):
    manager = make_session_manager(seeded_engine, timer_config=PACED_AI_TURNS)
    alice, bob = create_started_game(manager, player_names=["Alice", "Bob"])
    game = game_of(manager)
    alice_seat = participant_of(manager, alice).seat
    assert alice_seat is not None
    _discard_drawn_tile(manager, alice)
    scheduled = game.ai_turn
    assert scheduled is not None

    manager.disconnect(bob)
    assert game.ai_turn is scheduled

    _take_discarders(alice)
    discarders_per_delay = []
    for _ in range(3):
        await _end_held_sleeps(held_manager_sleep)
        discarders_per_delay.append(_take_discarders(alice))

    assert discarders_per_delay == [[(alice_seat + 1) % 4], [(alice_seat + 2) % 4], [(alice_seat + 3) % 4]]
    assert held_manager_sleep.durations.count(AI_TURN_DELAY) == 3
    assert (game.awaiting.kind, game.awaiting.seats) == (WaitKind.TURN, frozenset({alice_seat}))

    await manager.shutdown()


async def test_reconnect__when_its_ai_player_turn_is_still_delayed__should_cancel_it_and_open_the_human_turn(
    seeded_engine, held_manager_sleep
):
    manager = make_session_manager(seeded_engine, timer_config=PACED_AI_TURNS)
    alice, bob = create_started_game(manager, player_names=["Alice", "Bob"])
    game = game_of(manager)
    bob_participant = participant_of(manager, bob)
    bob_seat = bob_participant.seat
    _discard_drawn_tile(manager, alice)
    for _ in range(2):
        await _end_held_sleeps(held_manager_sleep)

    assert (game.awaiting.kind, game.awaiting.seats) == (WaitKind.TURN, frozenset({bob_seat}))
    decision_before = bob_participant.decision_id
    manager.disconnect(bob)
    delayed_ai_turn = game.ai_turn
    assert delayed_ai_turn is not None

    returning_bob = MockConnection(game_id="game1")
    manager.register_connection(returning_bob)
    manager.reconnect(returning_bob, session_token=bob_participant.ticket)
    _take_discarders(alice)
    await _end_held_sleeps(held_manager_sleep)
    assert delayed_ai_turn.cancelled()
    assert (game.awaiting.kind, game.awaiting.seats, game.ai_turn) == (WaitKind.TURN, frozenset({bob_seat}), None)
    assert (bob_participant.decision_id, bob_participant.timer.task is not None) == (decision_before + 1, True)
    resent_draws = [m for m in returning_bob.sent_messages if m.get(WireKey.EVENT_TYPE) == DRAW_T]
    assert [m[WireKey.WAIT_ID] for m in resent_draws] == [decision_before + 1]
    assert _take_discarders(alice) == []

    _discard_drawn_tile(manager, returning_bob)
    assert _take_discarders(alice) == [bob_seat]

    await manager.shutdown()


async def test_ai_turn_delay__when_the_last_human_leaves_during_it__should_abandon_the_game_without_the_ai_turn(
    seeded_engine, held_manager_sleep
):
    manager = make_session_manager(seeded_engine, timer_config=PACED_AI_TURNS)
    [alice] = create_started_game(manager, player_names=["Alice"])
    game = game_of(manager)
    _discard_drawn_tile(manager, alice)
    delayed_ai_turn = game.ai_turn
    assert delayed_ai_turn is not None

    manager.disconnect(alice)
    await _end_held_sleeps(held_manager_sleep)
    assert (delayed_ai_turn.cancelled(), game.ai_turn) == (True, None)

    await wait_for_background_tasks(manager)
    assert [finish.end_reason for finish in manager._game_repository.finishes] == [GameEndReason.ABANDONED]
