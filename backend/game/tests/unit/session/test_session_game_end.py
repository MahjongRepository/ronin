import asyncio
import gzip
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from mahjong.tile import TilesConverter

from game.logic.ai_player import AIPlayer
from game.logic.enums import GameAction, TimeoutType, WaitKind
from game.logic.events import EventType, GameEndedEvent, GameEvent
from game.logic.exceptions import InvalidGameActionError, ScoringError
from game.logic.scoring import HandResult
from game.logic.types import PlayerStanding
from game.messaging.encoder import decode
from game.messaging.event_payload import WAIT_ID_KEY
from game.messaging.types import SessionErrorCode
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.session import manager as manager_module
from game.session.manager import SessionManager
from game.session.models import GameLifecycle, PlayerSpec
from game.session.replay_collector import ReplayCollector
from game.session.timer import TimerConfig
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import (
    MOCK_GAME_OVER,
    FakeGameRepository,
    MockConnection,
    MockGameService,
    mock_update,
)
from game.tests.unit.helpers import _update_player, _update_round_state
from game.wire.events import EVENT_TYPE_INT
from shared.dal.models import GameEndReason
from shared.storage import LocalReplayStorage, replay_file_path

from .helpers import (
    arrange_final_discard,
    create_started_game,
    current_wait_id,
    fire_turn_timer_now,
    game_of,
    participant_of,
    run_timeout,
    runtime_of,
    wait_for_background_tasks,
)


def _make_game_end_events() -> list[GameEvent]:
    return [
        GameEndedEvent(
            type=EventType.GAME_END,
            winner_seat=0,
            standings=[
                PlayerStanding(seat=0, score=25000, final_score=0),
            ],
            leftover_riichi_bonus=0,
            num_rounds=1,
        ),
    ]


class TestFailGame:
    async def test_fail_game__when_failed_twice__should_send_one_internal_error_record_one_error_and_close_with_1011(
        self,
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(repository=game_repo)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        game = game_of(manager)

        manager.fail_game(game, reason="engine fault", exc=RuntimeError("boom"))
        manager.fail_game(game, reason="engine fault again")
        assert game.lifecycle is GameLifecycle.ENDING
        assert manager.get_game("game1") is None

        await wait_for_background_tasks(manager)
        assert game.lifecycle is GameLifecycle.CLOSED
        for conn in conns:
            assert [m["code"] for m in conn.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
            assert conn._close_code == 1011
            assert conn._close_reason == "internal_error"

        assert game_repo.games["game1"].end_reason == GameEndReason.ERROR
        assert len(game_repo.finishes) == 1

    async def test_fail_game__when_game_still_pending__should_close_joined_player_and_drop_pending_game(self):
        game_repo = FakeGameRepository()
        manager = make_session_manager(repository=game_repo)
        manager.create_pending_game(
            game_id="game1",
            player_specs=[
                PlayerSpec(name="Alice", user_id="u0", game_ticket="ticket-0"),
                PlayerSpec(name="Bob", user_id="u1", game_ticket="ticket-1"),
            ],
        )
        conn = MockConnection()
        manager.register_connection(conn)
        manager.join_game(conn, session_token="ticket-0")
        timeout_task = game_of(manager).pending_timeout

        manager.fail_game(game_of(manager), reason="join failed")
        await wait_for_background_tasks(manager)
        assert timeout_task.cancelled()
        assert manager.pending_game_count == 0
        assert "ticket-1" not in manager._participants_by_ticket
        assert conn._close_code == 1011
        assert game_repo.finishes == []

    async def test_fail_game__when_its_record_replay_save_and_a_send_fail__should_log_them_and_still_close_the_rest(
        self, caplog, monkeypatch
    ):
        game_repo = FakeGameRepository()
        collector = MagicMock(spec=ReplayCollector)
        collector.save = AsyncMock(side_effect=KeyError("replay buffer"))
        manager = SessionManager(
            MockGameService(),
            replay_collector=collector,
            game_repository=game_repo,
            timer_config=TimerConfig(game_start_pause_seconds=0),
        )
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        conns[0].send_message = MagicMock(side_effect=ValueError("encoder broke"))
        monkeypatch.setattr(manager_module, "build_finish_record", MagicMock(side_effect=KeyError("seat 3")))

        with caplog.at_level(logging.ERROR):
            manager.fail_game(manager.get_game("game1"), reason="engine fault")
            await wait_for_background_tasks(manager)

        assert [r.msg["event"] for r in caplog.records if r.levelno == logging.ERROR] == [
            "game failed",
            "failed to save the replay of a finished game",
            "failed to record the finish of a game",
            "failed to close a connection of a failed game",
        ]
        assert game_repo.finishes == []
        assert conns[0]._close_code == 1011
        assert conns[1]._close_code == 1011

    async def test_pending_game_timeout__when_game_start_raises__should_fail_the_game(self):
        game_service = MockGameService()
        game_service.start_game = MagicMock(side_effect=RuntimeError("start failed"))
        manager = make_session_manager(
            game_service, timer_config=TimerConfig(pending_game_timeout_seconds=0.01, game_start_pause_seconds=0)
        )
        manager.create_pending_game(
            game_id="game1",
            player_specs=[
                PlayerSpec(name="Alice", user_id="u0", game_ticket="ticket-0"),
                PlayerSpec(name="Bob", user_id="u1", game_ticket="ticket-1"),
            ],
        )
        conn = MockConnection()
        manager.register_connection(conn)
        manager.join_game(conn, session_token="ticket-0")

        timeout_task = game_of(manager).pending_timeout
        assert timeout_task is not None

        await timeout_task
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert [m["code"] for m in conn.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert conn._close_code == 1011

    async def test_game_action__when_the_scoring_library_fails_on_tsumo__should_fail_the_game_with_that_error(
        self, seeded_engine, caplog
    ):
        manager = make_session_manager(seeded_engine)
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        winning_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="12355"))
        _update_player(runtime_of(manager), seat=alice_seat, tiles=winning_hand)
        _update_round_state(runtime_of(manager), current_player_seat=alice_seat, pending_call_prompt=None)

        with (
            patch("game.logic.turn.calculate_hand_value", return_value=HandResult(error="library failure")),
            caplog.at_level(logging.ERROR),
        ):
            router.handle_message(
                conns[0],
                {
                    "t": WireClientMessageType.GAME_ACTION,
                    "wi": current_wait_id(manager),
                    "a": WireGameAction.DECLARE_TSUMO,
                },
            )
            await wait_for_background_tasks(manager)

        failure = next(r.msg for r in caplog.records if r.msg["event"] == "game failed")
        assert failure["reason"] == "game action failed"
        assert isinstance(failure["exc_info"], ScoringError)
        assert manager.get_game("game1") is None
        assert (conns[0]._close_code, conns[0]._close_reason) == (1011, "internal_error")

    async def test_game_action__when_an_ai_turn_after_the_committed_discard_is_refused__should_fail_the_game(
        self, seeded_engine, monkeypatch
    ):
        manager = make_session_manager(seeded_engine)
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        round_state = runtime_of(manager).state.round_state
        assert round_state.current_player_seat == alice_seat
        assert round_state.pending_call_prompt is None

        def discard_a_tile_not_in_hand(_ai_player, player, _round_state):
            return next(t for t in range(136) if t not in player.tiles)

        monkeypatch.setattr(AIPlayer, "select_discard", discard_a_tile_not_in_hand)
        router.handle_message(
            conns[0],
            {
                "t": WireClientMessageType.GAME_ACTION,
                "wi": current_wait_id(manager),
                "a": WireGameAction.DISCARD,
                "ti": round_state.players[alice_seat].tiles[-1],
            },
        )
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert (conns[0]._close_code, conns[0]._close_reason) == (1011, "internal_error")

    async def test_fail_game__when_the_game_id_is_reused_before_the_finalizer_runs__should_leave_the_new_game_alone(
        self, seeded_engine, tmp_path
    ):
        manager = make_session_manager(seeded_engine, storage=LocalReplayStorage(tmp_path))
        old_conns = create_started_game(manager, player_names=["Alice"])
        manager.fail_game(game_of(manager), reason="engine fault")

        new_conns = create_started_game(manager, player_names=["Bob"])
        await wait_for_background_tasks(manager)
        assert old_conns[0]._close_code == 1011
        assert replay_file_path(tmp_path, "game1").exists()
        assert not new_conns[0].is_closed
        new_game = game_of(manager)
        assert new_game.lifecycle is GameLifecycle.PLAYING
        assert new_game.replay is not None

        await manager.shutdown()


class TestGameEndOwnership:
    async def test_game_end__when_the_game_fails_while_its_replay_is_saved__should_stay_the_only_finish(
        self, seeded_engine, tmp_path, monkeypatch
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(seeded_engine, repository=game_repo, storage=LocalReplayStorage(tmp_path))
        collector = manager._replay_collector
        conns = create_started_game(manager, player_names=["Alice"])
        alice = conns[0]
        alice_seat = participant_of(manager, alice).seat
        game = game_of(manager)
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        replay_saving = asyncio.Event()
        resume_saving = asyncio.Event()
        save = collector.save

        async def pause_the_replay_save(game_id: str, lines: list[str]) -> None:
            replay_saving.set()
            await resume_saving.wait()
            await save(game_id, lines)

        monkeypatch.setattr(collector, "save", pause_the_replay_save)
        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await replay_saving.wait()

        manager.fail_game(game, reason="engine fault")
        resume_saving.set()
        await wait_for_background_tasks(manager)
        assert (alice._close_code, alice._close_reason) == (1000, "game_ended")
        assert SessionErrorCode.INTERNAL_ERROR not in [m.get("code") for m in alice.sent_messages]
        assert len(game_repo.finishes) == 1
        assert game_repo.games["game1"].end_reason == GameEndReason.COMPLETED

    async def test_game_end__when_sending_the_end_raises_unexpectedly__should_end_as_a_persisted_failure(
        self, seeded_engine, tmp_path, monkeypatch
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(seeded_engine, repository=game_repo, storage=LocalReplayStorage(tmp_path))
        conns = create_started_game(manager, player_names=["Alice"])
        alice = conns[0]
        alice_seat = participant_of(manager, alice).seat
        game = game_of(manager)
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        send_bytes = alice.send_bytes

        def fail_on_game_end(data: bytes) -> None:
            if decode(data).get("t") == EVENT_TYPE_INT[EventType.GAME_END]:
                raise ValueError("game end payload rejected")

            send_bytes(data)

        monkeypatch.setattr(alice, "send_bytes", fail_on_game_end)

        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await wait_for_background_tasks(manager)
        assert game_repo.games["game1"].end_reason == GameEndReason.ERROR
        assert game_repo.games["game1"].ended_at is not None
        assert replay_file_path(tmp_path, "game1").exists()
        assert [m.get("code") for m in alice.sent_messages][-1] == SessionErrorCode.INTERNAL_ERROR
        assert (alice._close_code, alice._close_reason) == (1011, "internal_error")
        assert manager.get_game("game1") is None
        assert game.runtime is None


class TestGameEndFromAction:
    async def test_game_end__when_ai_replacement_after_a_kick_ends_game__should_close_remaining_with_1000(
        self, manager
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=mock_update(_make_game_end_events(), MOCK_GAME_OVER),
        )
        manager._game_service.handle_action = MagicMock(
            side_effect=InvalidGameActionError(action="discard", seat=0, reason="tile not in hand"),
        )

        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        await wait_for_background_tasks(manager)
        assert (conns[0]._close_code, conns[0]._close_reason) == (1008, "invalid_game_action")
        assert (conns[1]._close_code, conns[1]._close_reason) == (1000, "game_ended")

    async def test_game_end__when_action_ends_game__should_release_the_game_at_once_and_then_close_all_connections(
        self, manager
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(
            return_value=mock_update(_make_game_end_events(), MOCK_GAME_OVER)
        )

        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        assert (manager.game_count, manager.get_playing_game_id("user-0")) == (0, None)

        await wait_for_background_tasks(manager)
        assert [(conn._close_code, conn._close_reason) for conn in conns] == [(1000, "game_ended")] * 2


class TestGameEndFromTimeout:
    async def test_game_end__when_turn_timer_fires_on_final_discard__should_save_replay_record_finish_and_close(
        self, seeded_engine, tmp_path
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(seeded_engine, repository=game_repo, storage=LocalReplayStorage(tmp_path))
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = (participant_of(manager, conn) for conn in conns)
        arrange_final_discard(runtime_of(manager), seat=alice.seat)

        assert manager.get_playing_game_id("user-0") == "game1"

        game = game_of(manager)
        timed_out = game.awaiting
        bob_timer = bob.timer
        manager._start_meld_timer(bob)
        await fire_turn_timer_now(manager, game_id="game1", seat=alice.seat)
        await wait_for_background_tasks(manager)
        final_wait = game.awaiting
        assert (final_wait.kind, final_wait.wait_id) == (WaitKind.NONE, timed_out.wait_id + 1)
        assert bob_timer.task is None
        assert manager.get_playing_game_id("user-0") is None
        assert game_repo.games["game1"].end_reason == GameEndReason.COMPLETED
        assert game_repo.games["game1"].ended_at is not None
        replay_text = gzip.decompress(replay_file_path(tmp_path, "game1").read_bytes()).decode()
        replay_lines = [json.loads(line) for line in replay_text.splitlines()]
        assert EVENT_TYPE_INT[EventType.DRAW] in [line.get("t") for line in replay_lines]
        assert [line for line in replay_lines if WAIT_ID_KEY in line] == []
        assert [(c._close_code, c._close_reason) for c in conns] == [(1000, "game_ended"), (1000, "game_ended")]

    async def test_game_message__when_sent_after_the_end_claim_before_the_close__should_get_no_answer(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = participant_of(manager, conns[0]).seat
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        assert manager.get_game("game1") is None

        manager.handle_game_action(conns[1], action=GameAction.PASS, data={}, wait_id=0)
        await wait_for_background_tasks(manager)
        assert conns[1].sent_messages[-1]["t"] == EVENT_TYPE_INT[EventType.GAME_END]
        assert (conns[1]._close_code, conns[1]._close_reason) == (1000, "game_ended")


class TestGameEndFromDisconnect:
    async def test_game_end__when_ai_replacement_after_leave_ends_game__should_close_remaining_with_1000(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=mock_update(_make_game_end_events(), MOCK_GAME_OVER),
        )

        manager.disconnect(conns[0])
        await wait_for_background_tasks(manager)
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"
