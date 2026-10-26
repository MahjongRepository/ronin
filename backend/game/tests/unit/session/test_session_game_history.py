from unittest.mock import MagicMock

import pytest

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import EventType, GameEndedEvent, ServiceEvent
from game.logic.types import PlayerStanding
from game.session.models import GameLifecycle, PlayerSpec
from game.session.timer import TimerConfig
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MOCK_GAME_OVER, FakeGameRepository, MockConnection, mock_update
from shared.dal.models import GameEndReason

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


@pytest.fixture
def game_repo():
    return FakeGameRepository()


@pytest.fixture
def manager_with_repo(game_repo):
    return make_session_manager(repository=game_repo)


def _make_game_end_events(*, num_rounds: int = 1) -> list[ServiceEvent]:
    return [
        ServiceEvent(
            data=GameEndedEvent(
                type=EventType.GAME_END,
                winner_seat=0,
                standings=[
                    PlayerStanding(seat=0, score=25000, final_score=0),
                ],
                leftover_riichi_bonus=0,
                num_rounds=num_rounds,
            ),
        ),
    ]


def _seat_rows(game_repo: FakeGameRepository) -> list[tuple[int, str, str, int | None]]:
    return [(s.seat, s.name, s.user_id, s.score) for s in game_repo.games["game1"].standings]


class TestGameStartRecording:
    async def test_game_history__when_game_starts__should_record_every_seat_in_seat_order(
        self, manager_with_repo, game_repo
    ):
        create_started_game(manager_with_repo, player_names=["Alice", "Bob"])

        recorded = game_repo.games["game1"]
        assert (recorded.game_type, recorded.ended_at, recorded.end_reason) == ("hanchan", None, None)
        assert _seat_rows(game_repo) == [
            (0, "Alice", "user-0", None),
            (1, "Bob", "user-1", None),
            (2, "AI", "", None),
            (3, "AI", "", None),
        ]

    async def test_start_game__when_human_is_named_like_an_ai__should_seat_them_and_record_their_user_id(
        self, seeded_engine, game_repo
    ):
        manager = make_session_manager(seeded_engine, repository=game_repo)
        conns = create_started_game(manager, player_names=["Tsumogiri 1"])
        human_seat = participant_of(manager, conns[0]).seat
        assert human_seat is not None
        ai_seats = sorted(set(range(4)) - {human_seat})
        standings = {s.seat: (s.name, s.user_id) for s in game_repo.games["game1"].standings}
        assert standings == {
            human_seat: ("Tsumogiri 1", "user-0"),
            **{seat: (f"Tsumogiri {number}", "") for number, seat in enumerate(ai_seats, start=2)},
        }

        human = runtime_of(manager).state.round_state.players[human_seat]
        assert runtime_of(manager).state.round_state.current_player_seat == human_seat
        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": human.tiles[-1]}, wait_id=current_wait_id(manager)
        )
        human_after = runtime_of(manager).state.round_state.players[human_seat]
        assert [d.tile_id for d in human_after.discards] == [human.tiles[-1]]
        assert game_of(manager).lifecycle is GameLifecycle.PLAYING


class TestGameCompletionRecording:
    async def test_game_history__when_game_ends__should_record_standings_in_placement_order_and_round_count(
        self, manager_with_repo, game_repo
    ):
        conns = create_started_game(manager_with_repo, player_names=["Alice", "Bob"])
        events = [
            ServiceEvent(
                data=GameEndedEvent(
                    type=EventType.GAME_END,
                    winner_seat=1,
                    standings=[
                        PlayerStanding(seat=1, score=40000, final_score=50),
                        PlayerStanding(seat=0, score=25000, final_score=0),
                        PlayerStanding(seat=2, score=20000, final_score=-15),
                        PlayerStanding(seat=3, score=15000, final_score=-35),
                    ],
                    leftover_riichi_bonus=0,
                    num_rounds=8,
                ),
            ),
        ]
        manager_with_repo._game_service.handle_action = MagicMock(return_value=mock_update(events, MOCK_GAME_OVER))

        manager_with_repo.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager_with_repo)
        )
        await wait_for_background_tasks(manager_with_repo)
        recorded = game_repo.games["game1"]
        assert recorded.end_reason == GameEndReason.COMPLETED
        assert recorded.ended_at is not None
        assert recorded.num_rounds_played == 8
        assert [(s.seat, s.name, s.user_id, s.score, s.final_score) for s in recorded.standings] == [
            (1, "Bob", "user-1", 40000, 50),
            (0, "Alice", "user-0", 25000, 0),
            (2, "AI", "", 20000, -15),
            (3, "AI", "", 15000, -35),
        ]

    async def test_game_history__when_timeout_ends_game__should_record_completed(self, manager_with_repo, game_repo):
        create_started_game(manager_with_repo, player_names=["Alice", "Bob"])
        manager_with_repo._game_service.handle_timeout = MagicMock(
            return_value=mock_update(_make_game_end_events(), MOCK_GAME_OVER)
        )

        run_timeout(manager_with_repo, game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        await wait_for_background_tasks(manager_with_repo)
        assert game_repo.games["game1"].end_reason == GameEndReason.COMPLETED

    async def test_game_history__when_a_human_never_connected__should_keep_their_seat_in_the_finish_standings(
        self, seeded_engine, game_repo
    ):
        manager = make_session_manager(
            seeded_engine,
            repository=game_repo,
            timer_config=TimerConfig(pending_game_timeout_seconds=0.01, game_start_pause_seconds=0),
        )
        manager.create_pending_game(
            game_id="game1",
            player_specs=[
                PlayerSpec(name="Alice", user_id="user-0", game_ticket="ticket-0"),
                PlayerSpec(name="Bob", user_id="user-1", game_ticket="ticket-1"),
            ],
        )
        alice = MockConnection()
        manager.register_connection(alice)
        manager.join_game(alice, session_token="ticket-0")
        pending_timeout = game_of(manager).pending_timeout
        assert pending_timeout is not None
        await pending_timeout
        alice_seat = participant_of(manager, alice).seat
        bob_seat = manager._participants_by_ticket["ticket-1"].seat
        arrange_final_discard(runtime_of(manager), seat=alice_seat)

        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await wait_for_background_tasks(manager)
        recorded = game_repo.games["game1"]
        assert recorded.end_reason == GameEndReason.COMPLETED
        assert sorted((s.seat, s.user_id) for s in recorded.standings) == sorted(
            [
                (alice_seat, "user-0"),
                (bob_seat, "user-1"),
                *((seat, "") for seat in {0, 1, 2, 3} - {alice_seat, bob_seat}),
            ]
        )
        assert {s.name for s in recorded.standings if s.seat == bob_seat} == {"Bob"}
        assert all(s.score is not None for s in recorded.standings)


class TestGameAbandonmentRecording:
    async def test_game_history__when_all_players_leave__should_record_abandoned_with_the_seat_order_roster(
        self, manager_with_repo, game_repo
    ):
        conns = create_started_game(manager_with_repo, player_names=["Alice"])

        manager_with_repo.disconnect(conns[0])
        await wait_for_background_tasks(manager_with_repo)
        recorded = game_repo.games["game1"]
        assert recorded.end_reason == GameEndReason.ABANDONED
        assert recorded.ended_at is not None
        assert _seat_rows(game_repo) == [
            (0, "Alice", "user-0", None),
            (1, "AI", "", None),
            (2, "AI", "", None),
            (3, "AI", "", None),
        ]

    async def test_game_history__when_completed_game_cleaned_up__should_not_record_abandoned(
        self, manager_with_repo, game_repo
    ):
        conns = create_started_game(manager_with_repo, player_names=["Alice", "Bob"])
        manager_with_repo._game_service.handle_action = MagicMock(
            return_value=mock_update(_make_game_end_events(), MOCK_GAME_OVER)
        )

        manager_with_repo.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager_with_repo)
        )
        for conn in conns:
            manager_with_repo.disconnect(conn)
        await wait_for_background_tasks(manager_with_repo)
        assert manager_with_repo.get_game("game1") is None
        assert [game.end_reason for game in game_repo.finishes] == [GameEndReason.COMPLETED]
