import json
import logging
from typing import TYPE_CHECKING

import pytest

from game.logic.enums import GameAction
from game.logic.events import (
    DiscardEvent,
    GameEndedEvent,
)
from game.logic.exceptions import GeneratedActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.logic.types import PlayerStanding
from game.messaging.types import SessionErrorCode
from game.server.types import PlayerSpec
from game.session.replay_collector import ReplayCollector
from game.session.timer import TimerConfig
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import (
    MOCK_AWAITING,
    MOCK_GAME_OVER,
    FailingReplayStorage,
    FakeGameRepository,
    FakeReplayStorage,
    MockConnection,
)
from game.wire.compact import decode_discard
from game.wire.enums import WireEventType
from scripts.replay_fixtures.staged_game import PLAYERS, STAGED_SEED, Seating, StagedGame, StagedWall
from shared.dal.models import GameEndReason

from .helpers import (
    ENGINE_SEED,
    arrange_final_discard,
    create_started_game,
    current_wait_id,
    disconnect_and_reconnect,
    game_of,
    participant_of,
    runtime_of,
    wait_for_background_tasks,
)

if TYPE_CHECKING:
    from game.logic.service import GameStart
    from game.session.manager import SessionManager


NO_CALLS_WALL = StagedWall(
    hands=(
        tile_copies(1, man="147", pin="147", sou="147", honors="1234"),
        tile_copies(2, man="258", pin="258", sou="258", honors="1234"),
        tile_copies(0, man="369", pin="369", sou="369", honors="1234"),
        tile_copies(3, man="369", pin="369", sou="369", honors="1234"),
    ),
)


class StagedWallEngine(MahjongGameService):
    def __init__(self, staged: StagedWall) -> None:
        super().__init__()
        self._wall = list(staged.tiles())

    def start_game(self, game_id: str, player_names: list[str], **_options: object) -> GameStart:
        return super().start_game(game_id, player_names, seed=STAGED_SEED, wall=self._wall)


def _join(manager: SessionManager, ticket: str) -> MockConnection:
    connection = MockConnection(game_id="game1")
    manager.register_connection(connection)
    manager.join_game(connection, session_token=ticket)
    return connection


def _reconnect(manager: SessionManager, ticket: str) -> MockConnection:
    connection = MockConnection(game_id="game1")
    manager.register_connection(connection)
    manager.reconnect(connection, session_token=ticket)
    return connection


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

    async def test_disconnect__when_the_ai_player_cannot_move__should_record_no_ai_replacement(
        self, seeded_engine, monkeypatch
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        replay = game_of(manager).replay

        def refuse_the_ai_move(*_args: object) -> None:
            raise GeneratedActionError("AI seat returned no turn action")

        monkeypatch.setattr(seeded_engine, "process_ai_player_actions_after_replacement", refuse_the_ai_move)
        with pytest.raises(GeneratedActionError):
            manager.disconnect(conns[0])
        assert [line for line in replay.lines if json.loads(line)["t"] == 101] == []

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

    async def test_seat_control_lines__when_absent_then_left_then_back__should_match_the_fixture_generator(
        self,
    ):
        manager = make_session_manager(
            StagedWallEngine(NO_CALLS_WALL),
            timer_config=TimerConfig(pending_game_timeout_seconds=0.01, game_start_pause_seconds=0),
        )
        specs = [PlayerSpec(name=name, user_id=f"user-{name}", game_ticket=f"ticket-{name}") for name in PLAYERS]
        manager.create_pending_game(game_id="game1", player_specs=specs)
        alice, *_ = [_join(manager, f"ticket-{name}") for name in PLAYERS[:3]]
        game = game_of(manager)
        assert game.pending_timeout is not None

        await game.pending_timeout
        alice_seat, diana_seat = participant_of(manager, alice).seat, game.participants[3].seat
        assert diana_seat == runtime_of(manager).state.round_state.dealer_seat
        assert game.awaiting is not None
        assert game.awaiting.seats == {alice_seat}

        manager.disconnect(alice)
        _reconnect(manager, "ticket-Diana")
        staged = StagedGame("game1", NO_CALLS_WALL, seating=Seating(absent=frozenset({diana_seat})))
        staged.leave(alice_seat)
        staged.restore_human(diana_seat)
        seat_controls = [line for line in map(json.loads, game.replay.lines) if line["t"] == 101]
        assert [line["s"] for line in seat_controls] == [diana_seat, alice_seat, diana_seat]
        assert game.replay.lines == list(staged._recorder.recording().lines)

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
