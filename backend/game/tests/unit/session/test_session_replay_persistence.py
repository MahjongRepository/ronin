import json
import logging

from game.logic.enums import GameAction, TimeoutType, WaitKind
from game.logic.events import (
    DiscardEvent,
    GameEndedEvent,
)
from game.logic.rng import RNG_VERSION
from game.logic.types import PlayerStanding
from game.messaging.types import SessionErrorCode
from game.session.replay_collector import ReplayCollector
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import (
    MOCK_AWAITING,
    MOCK_GAME_OVER,
    FailingReplayStorage,
    FakeGameRepository,
    FakeReplayStorage,
)
from game.wire.compact import decode_discard
from game.wire.enums import WireEventType
from shared.dal.models import GameEndReason

from .helpers import (
    ENGINE_SEED,
    arrange_final_discard,
    arrange_ron_and_pon_on_a_discard,
    create_started_game,
    current_wait_id,
    disconnect_and_reconnect,
    game_of,
    participant_of,
    run_timeout,
    runtime_of,
    wait_for_background_tasks,
)


def _make_game_end_event() -> GameEndedEvent:
    return GameEndedEvent(
        winner_seat=0,
        standings=[PlayerStanding(seat=0, score=25000, final_score=0)],
        leftover_riichi_bonus=0,
        num_rounds=1,
    )


def _make_discard_event() -> DiscardEvent:
    return DiscardEvent(seat=0, tile_id=10)


class TestReplayCollectorMerge:
    def test_replay_collector_merge__when_no_payloads__should_return_empty_json(self):
        result = ReplayCollector._merge_round_started_payloads([])
        assert result == "{}"


class TestSessionReplay:
    async def test_replay_start__when_game_starts__should_record_with_the_engine_seed_and_settings(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        create_started_game(manager)

        replay = game_of(manager).replay
        assert replay is not None
        engine_settings = runtime_of(manager).state.settings
        assert (replay.seed, replay.rng_version, replay.settings) == (ENGINE_SEED, RNG_VERSION, engine_settings)
        await manager.shutdown()

    async def test_replay_collect__when_events_broadcast__should_append_them_without_saving(self):
        storage = FakeReplayStorage()
        manager = make_session_manager(storage=storage)
        create_started_game(manager)
        game = game_of(manager)
        recorded_before = len(game.replay.lines)

        manager._broadcast_events(game, [_make_discard_event()], MOCK_AWAITING)
        await wait_for_background_tasks(manager)
        assert len(game.replay.lines) == recorded_before + 1
        assert storage.saved == {}

    async def test_replay_save__when_game_end_event__should_save_the_detached_lines(self):
        storage = FakeReplayStorage()
        manager = make_session_manager(storage=storage)
        create_started_game(manager)
        game = game_of(manager)

        manager._broadcast_events(game, [_make_game_end_event()], MOCK_GAME_OVER)
        assert game.replay is None

        await wait_for_background_tasks(manager)
        assert list(storage.saved) == ["game1"]

    async def test_replay_save__when_storage_fails_after_a_completion__should_record_an_error_end_and_close_with_1011(
        self, seeded_engine, caplog
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(seeded_engine, repository=game_repo, storage=FailingReplayStorage())
        conns = create_started_game(manager)
        alice_seat = participant_of(manager, conns[0]).seat
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        drawn_tile = runtime_of(manager).state.round_state.players[alice_seat].tiles[-1]

        with caplog.at_level(logging.ERROR):
            manager.handle_game_action(
                conns[0], action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=current_wait_id(manager)
            )
            await wait_for_background_tasks(manager)
        assert [(r.msg["event"], r.msg["game_id"], "seat" in r.msg) for r in caplog.records] == [
            ("failed to save the replay of a finished game", "game1", False)
        ]
        assert game_repo.games["game1"].end_reason == GameEndReason.ERROR
        assert [m.get("code") for m in conns[0].sent_messages][-1] == SessionErrorCode.INTERNAL_ERROR
        assert (conns[0]._close_code, conns[0]._close_reason) == (1011, "internal_error")

    async def test_handle_timeout__when_turn_times_out__should_record_the_timeout_before_the_default_discard(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        replay = game_of(manager).replay
        recorded_before = len(replay.lines)

        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        timeout_line, default_discard, *_ = (json.loads(line) for line in replay.lines[recorded_before:])
        assert timeout_line == {"t": 100, "s": alice_seat, "k": 0}
        assert default_discard["t"] == WireEventType.DISCARD
        assert decode_discard(default_discard["d"])[0] == alice_seat

        await manager.shutdown()

    async def test_handle_timeout__when_call_prompt_times_out__should_record_only_the_timeout_line(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        alice, bob, carol = (participant_of(manager, conn).seat for conn in conns)
        discarded_four_pin = arrange_ron_and_pon_on_a_discard(runtime_of(manager), discarder=alice, ron=bob, pon=carol)
        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": discarded_four_pin}, wait_id=current_wait_id(manager)
        )
        replay = game_of(manager).replay
        recorded_before = len(replay.lines)

        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.MELD, seat=carol)
        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.MELD, seat=carol)
        assert [json.loads(line) for line in replay.lines[recorded_before:]] == [{"t": 100, "s": carol, "k": 1}]
        assert (game_of(manager).awaiting.kind, game_of(manager).awaiting.seats) == (WaitKind.CALL, frozenset({bob}))

        await manager.shutdown()

    async def test_disconnect__when_game_playing__should_record_the_ai_replacement_before_its_moves(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = participant_of(manager, conns[0]).seat
        assert runtime_of(manager).state.round_state.current_player_seat == alice_seat
        replay = game_of(manager).replay
        recorded_before = len(replay.lines)

        manager.disconnect(conns[0])
        ai_replacement, ai_discard, *_ = (json.loads(line) for line in replay.lines[recorded_before:])
        assert ai_replacement == {"t": 101, "s": alice_seat, "ai": 1, "r": 0}
        assert ai_discard["t"] == WireEventType.DISCARD
        assert decode_discard(ai_discard["d"])[0] == alice_seat

        await manager.shutdown()

    async def test_reconnect__when_an_ai_player_held_the_seat__should_record_the_human_return(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = participant_of(manager, conns[0]).seat
        replay = game_of(manager).replay

        disconnect_and_reconnect(manager, conns[0])
        lines = [json.loads(line) for line in replay.lines]
        assert [line for line in lines if line["t"] == 101] == [
            {"t": 101, "s": alice_seat, "ai": 1, "r": 0},
            {"t": 101, "s": alice_seat, "ai": 0},
        ]
        assert lines[-1] == {"t": 101, "s": alice_seat, "ai": 0}

        await manager.shutdown()

    async def test_replay_discard__when_game_abandoned__should_save_nothing(self):
        storage = FakeReplayStorage()
        game_repo = FakeGameRepository()
        manager = make_session_manager(repository=game_repo, storage=storage)
        conns = create_started_game(manager)

        manager.disconnect(conns[0])
        await wait_for_background_tasks(manager)
        assert game_repo.games["game1"].end_reason == GameEndReason.ABANDONED
        assert storage.saved == {}
