from unittest.mock import AsyncMock

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, GameEndedEvent, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.logic.types import PlayerStanding
from game.session.models import Player
from game.tests.mocks import MockConnection, MockResultEvent

from .helpers import create_started_game, make_game_with_player


def _make_game_end_events() -> list[ServiceEvent]:
    return [
        ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                winner_seat=0,
                standings=[
                    PlayerStanding(seat=0, score=25000, final_score=0),
                ],
            ),
            target=BroadcastTarget(),
        ),
    ]


class TestSessionManagerGameEnd:
    def _make_game_end_event(self) -> ServiceEvent:
        return ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                winner_seat=0,
                standings=[
                    PlayerStanding(seat=0, score=25000, final_score=0),
                ],
            ),
            target=BroadcastTarget(),
        )

    async def test_game_end__when_game_end_event__should_close_connection_with_1000(self, manager):
        game, _player, conn = make_game_with_player(manager)

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)
        assert conn.is_closed is True
        assert conn._close_code == 1000
        assert conn._close_reason == "game_ended"

    async def test_game_end__when_events_lack_game_end__should_keep_connection_open(self, manager):
        game, _player, conn = make_game_with_player(manager)

        generic_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Alice",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        await manager._close_connections_on_game_end(game, [generic_event])
        assert conn.is_closed is False

    async def test_game_end__when_game_end_event_with_two_players__should_close_both(self, manager):
        game, _player, conn1 = make_game_with_player(manager)

        conn2 = MockConnection()
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
        game.players[conn2.connection_id] = player2

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)
        assert conn1.is_closed is True
        assert conn2.is_closed is True


class TestSessionManagerCloseGameOnError:
    async def test_close_game_on_error__when_player_in_game__should_close_all_with_1011(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        await manager.close_game_on_error(conns[0])
        assert conns[0].is_closed
        assert conns[1].is_closed
        assert conns[0]._close_code == 1011
        assert conns[0]._close_reason == "internal_error"

    async def test_close_game_on_error__when_connection_not_in_game__should_do_nothing(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        # should not raise
        await manager.close_game_on_error(conn)
        assert not conn.is_closed

    async def test_close_game_on_error__when_game_mapping_missing__should_keep_connection_open(self, manager):
        conns = await create_started_game(manager)

        # remove the game from the internal mapping to simulate cleanup race
        manager._games.pop("game1", None)

        # should return without error
        await manager.close_game_on_error(conns[0])
        # connection should NOT be closed (game is gone)
        assert not conns[0].is_closed

    async def test_heartbeat__when_game_cleaned_up__should_stop_game_task(self, manager):
        conns = await create_started_game(
            manager,
            num_ai_players=0,
            player_names=["P0", "P1", "P2", "P3"],
        )
        assert "game:game1" in manager._heartbeat._tasks
        heartbeat_task = manager._heartbeat._tasks.get("game:game1")

        # leave all players -- game becomes empty, cleanup runs
        for c in conns:
            await manager.leave_game(c)

        assert "game:game1" not in manager._heartbeat._tasks
        assert heartbeat_task.done()


class TestGameEndFromAction:
    async def test_game_end__when_action_ends_game__should_close_all_connections(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert conns[0].is_closed
        assert conns[0]._close_code == 1000
        assert conns[0]._close_reason == "game_ended"
        assert conns[1].is_closed

    async def test_game_end__when_ai_replacement_after_invalid_action_ends_game__should_close_remaining_with_1000(
        self, manager
    ):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )
        error = InvalidGameActionError(action="discard", seat=0, reason="bad tile")
        manager._game_service.handle_action = AsyncMock(side_effect=error)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        # Offender closed with 1008 (invalid action)
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        # Bob closed with 1000 (game ended via AI replacement)
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"


class TestGameEndFromTimeout:
    async def test_game_end__when_timeout_ends_game__should_close_all_connections(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_timeout = AsyncMock(return_value=_make_game_end_events())

        await manager._handle_timeout(game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        assert conns[0].is_closed
        assert conns[0]._close_code == 1000
        assert conns[0]._close_reason == "game_ended"
        assert conns[1].is_closed

    async def test_game_end__when_ai_replacement_after_timeout_ends_game__should_close_remaining_with_1000(
        self, manager
    ):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )
        error = InvalidGameActionError(action="pass", seat=0, reason="resolution failed")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        await manager._handle_timeout(game_id="game1", timeout_type=TimeoutType.MELD, seat=0)
        # Offender closed with 1008
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        # Bob closed with 1000 (game ended)
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000


class TestGameEndFromLeaveGame:
    async def test_game_end__when_ai_replacement_after_leave_ends_game__should_close_remaining_with_1000(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )

        await manager.leave_game(conns[0])
        # Bob's connection should be closed with game_ended
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"
