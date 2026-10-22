from unittest.mock import AsyncMock

from game.logic.events import (
    DiscardEvent,
    GameEndedEvent,
    ServiceEvent,
)
from game.logic.rng import RNG_VERSION
from game.logic.types import PlayerStanding
from game.messaging.types import SessionErrorCode
from game.session.replay_collector import ReplayCollector
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MOCK_AWAITING, MOCK_GAME_OVER, FakeGameRepository, FakeReplayStorage
from shared.dal.models import GameEndReason

from .helpers import ENGINE_SEED, create_started_game, game_of, wait_for_background_tasks


def _make_game_end_event() -> ServiceEvent:
    return ServiceEvent(
        data=GameEndedEvent(
            winner_seat=0,
            standings=[PlayerStanding(seat=0, score=25000, final_score=0)],
        ),
    )


def _make_discard_event() -> ServiceEvent:
    return ServiceEvent(data=DiscardEvent(seat=0, tile_id=10))


class TestReplayCollectorMerge:
    def test_replay_collector_merge__when_no_payloads__should_return_empty_json(self):
        result = ReplayCollector._merge_round_started_payloads([])
        assert result == "{}"


class TestSessionReplay:
    async def test_replay_start__when_game_starts__should_record_with_the_engine_seed(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        await create_started_game(manager)

        replay = game_of(manager).replay
        assert replay is not None
        assert (replay.seed, replay.rng_version) == (ENGINE_SEED, RNG_VERSION)
        await manager.shutdown()

    async def test_replay_collect__when_events_broadcast__should_append_them_without_saving(self):
        storage = FakeReplayStorage()
        manager = make_session_manager(storage=storage)
        await create_started_game(manager)
        game = game_of(manager)
        recorded_before = len(game.replay.lines)

        manager._broadcast_events(game, [_make_discard_event()], MOCK_AWAITING)
        await wait_for_background_tasks(manager)
        assert len(game.replay.lines) == recorded_before + 1
        assert storage.saved == {}

    async def test_replay_save__when_game_end_event__should_save_the_detached_lines(self):
        storage = FakeReplayStorage()
        manager = make_session_manager(storage=storage)
        await create_started_game(manager)
        game = game_of(manager)

        manager._broadcast_events(game, [_make_game_end_event()], MOCK_GAME_OVER)
        assert game.replay is None

        await wait_for_background_tasks(manager)
        assert list(storage.saved) == ["game1"]

    async def test_replay_save__when_it_raises_after_a_completion__should_record_an_error_end_and_close_with_1011(
        self, monkeypatch
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(repository=game_repo)
        conns = await create_started_game(manager)
        game = game_of(manager)
        monkeypatch.setattr(manager._replay_collector, "save", AsyncMock(side_effect=RuntimeError("disk gone")))

        manager._broadcast_events(game, [_make_game_end_event()], MOCK_GAME_OVER)
        await wait_for_background_tasks(manager)
        assert game_repo.games["game1"].end_reason == GameEndReason.ERROR
        assert [m.get("code") for m in conns[0].sent_messages][-1] == SessionErrorCode.INTERNAL_ERROR
        assert (conns[0]._close_code, conns[0]._close_reason) == (1011, "internal_error")

    async def test_replay_discard__when_game_abandoned__should_save_nothing(self):
        storage = FakeReplayStorage()
        game_repo = FakeGameRepository()
        manager = make_session_manager(repository=game_repo, storage=storage)
        conns = await create_started_game(manager)

        await manager.leave_game(conns[0])
        await wait_for_background_tasks(manager)
        assert game_repo.games["game1"].end_reason == GameEndReason.ABANDONED
        assert storage.saved == {}
