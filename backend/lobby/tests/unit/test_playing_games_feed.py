import asyncio
from types import SimpleNamespace

from app.game_transition import PlayingGame
from app.live_games.feed import PlayingGamesFeed

_GAMES = (PlayingGame(game_id="g1", started_at=1_700_000_000.0, game_type="hanchan", players=("A", "B", "C", "D")),)


class _Connection:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.received = asyncio.Event()

    def send_text(self, text: str) -> None:
        self.sent.append(text)
        self.received.set()

    async def first_message(self) -> None:
        async with asyncio.timeout(1):
            await self.received.wait()


async def test_playing_games_feed_watch__when_last_watcher_left_mid_interval__should_send_a_new_one_the_list_at_once():
    async def fetch() -> tuple[PlayingGame, ...]:
        return _GAMES

    feed = PlayingGamesFeed(fetch=fetch, interval_seconds=3600)
    feed.start()
    alice = SimpleNamespace(connection_id="alice", connection=_Connection())
    bob = SimpleNamespace(connection_id="bob", connection=_Connection())

    feed.watch(alice)
    await alice.connection.first_message()
    feed.unwatch(alice)
    feed.watch(bob)
    await bob.connection.first_message()
    await feed.stop()

    assert bob.connection.sent == alice.connection.sent
    assert len(bob.connection.sent) == 1
