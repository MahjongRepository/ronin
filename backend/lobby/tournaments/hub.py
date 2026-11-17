from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from lobby.players import LobbyPlayer

TOURNAMENT_DELETED = "tournament_deleted"
_DELETED_CLOSE_CODE = 4000
HISTORY_MAX_AGE_SECONDS = 24 * 60 * 60
HISTORY_MAX_ENTRIES = 1000


@dataclass(frozen=True, slots=True)
class _HistoryEntry:
    time: float
    event: dict[str, object]


class TournamentHub:
    """
    The players online on each tournament's page, one connection per user, and its events subscribers, in memory only.

    A subscriber is keyed by connection, so one user may hold several; it is never online, it only receives what
    ``publish`` sends. It also keeps each tournament's recent history, the lines its page shows from server events
    (chat, games started and ended, players coming online and going offline), lost on a restart like the rest. Every
    method is one synchronous step on the event loop, so no lock is needed.
    """

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._online: dict[str, dict[str, LobbyPlayer]] = {}
        self._subscribers: dict[str, dict[str, LobbyPlayer]] = {}
        self._history: dict[str, deque[_HistoryEntry]] = {}
        self._clock = clock

    def connect(self, tournament_id: str, player: LobbyPlayer) -> LobbyPlayer | None:
        """
        Put the player online in the tournament; return the same user's connection it replaced, if any.

        A replaced user keeps their place in the connect order.
        """
        players = self._online.setdefault(tournament_id, {})
        replaced = players.get(player.user_id)
        players[player.user_id] = player
        return replaced

    def disconnect(self, tournament_id: str, player: LobbyPlayer) -> bool:
        """
        Take the player's connection offline; return False when it is not the user's current one.
        """
        players = self._online.get(tournament_id, {})
        if players.get(player.user_id) is not player:
            return False

        del players[player.user_id]
        if not players:
            del self._online[tournament_id]

        return True

    def online_names(self, tournament_id: str) -> list[str]:
        """
        Return the usernames online in the tournament, in connect order.
        """
        return [player.username for player in self._online.get(tournament_id, {}).values()]

    def find_online(self, tournament_id: str, username: str) -> LobbyPlayer | None:
        """
        Return the connection of the user online in the tournament whose username matches, ignoring case, or None.

        Usernames are unique ignoring case, so at most one matches.
        """
        wanted = username.casefold()
        players = self._online.get(tournament_id, {}).values()
        return next((player for player in players if player.username.casefold() == wanted), None)

    def subscribe(self, tournament_id: str, subscriber: LobbyPlayer) -> None:
        """
        Add an events subscriber to the tournament.
        """
        self._subscribers.setdefault(tournament_id, {})[subscriber.connection_id] = subscriber

    def unsubscribe(self, tournament_id: str, subscriber: LobbyPlayer) -> None:
        """
        Remove an events subscriber from the tournament.
        """
        subscribers = self._subscribers.get(tournament_id, {})
        subscribers.pop(subscriber.connection_id, None)
        if not subscribers:
            self._subscribers.pop(tournament_id, None)

    def presence(self, tournament_id: str) -> dict[str, object]:
        """
        Return the tournament's ``presence`` event: the online names and their count.
        """
        names = self.online_names(tournament_id)
        return {"type": "presence", "players": names, "count": len(names)}

    def broadcast_presence(self, tournament_id: str, *, exclude: str | None = None) -> None:
        """
        Publish the tournament's ``presence`` event; ``exclude`` skips one player connection.
        """
        self.publish(tournament_id, self.presence(tournament_id), exclude=exclude)

    def publish(self, tournament_id: str, event: Mapping[str, object], *, exclude: str | None = None) -> None:
        """
        Send a tournament event, encoded once, to every player online and every events subscriber.

        ``exclude`` skips one player connection.
        """
        payload = json.dumps(event)
        self._send_to_players(tournament_id, payload, exclude=exclude)
        for subscriber in self._subscribers.get(tournament_id, {}).values():
            subscriber.connection.send_text(payload)

    def broadcast(self, tournament_id: str, message: Mapping[str, object], *, exclude: str | None = None) -> None:
        """
        Send a message to the players online in the tournament only, encoded once; ``exclude`` skips one connection.
        """
        self._send_to_players(tournament_id, json.dumps(message), exclude=exclude)

    def record(self, tournament_id: str, entry: Mapping[str, object]) -> dict[str, object]:
        """
        Keep a line the tournament page shows in the tournament's history; return the entry with its epoch-seconds time.

        Every tournament's history drops its entries older than ``HISTORY_MAX_AGE_SECONDS`` when it gains one, and keeps
        at most the newest ``HISTORY_MAX_ENTRIES``; a history whose newest entry is that old is dropped.
        """
        now = self._clock()
        cutoff = now - HISTORY_MAX_AGE_SECONDS
        for stale_id in [stale_id for stale_id, entries in self._history.items() if entries[-1].time < cutoff]:
            del self._history[stale_id]

        kept = _HistoryEntry(time=now, event={**entry, "time": now})
        entries = self._history.setdefault(tournament_id, deque(maxlen=HISTORY_MAX_ENTRIES))
        entries.append(kept)
        while entries[0].time < cutoff:
            entries.popleft()

        return kept.event

    def history(self, tournament_id: str) -> list[dict[str, object]]:
        """
        Return the tournament's kept entries, oldest first.
        """
        return [entry.event for entry in self._history.get(tournament_id, ())]

    def close_deleted_tournament(self, tournament_id: str) -> None:
        """
        Tell every player connection and events subscriber of a deleted tournament ``tournament_deleted``, close them
        and forget them all with its history.
        """
        self._history.pop(tournament_id, None)
        players = self._online.pop(tournament_id, {})
        subscribers = self._subscribers.pop(tournament_id, {})
        for connection in [*players.values(), *subscribers.values()]:
            connection.send({"type": "error", "message": TOURNAMENT_DELETED})
            connection.connection.close(code=_DELETED_CLOSE_CODE, reason=TOURNAMENT_DELETED)

    def _send_to_players(self, tournament_id: str, payload: str, *, exclude: str | None) -> None:
        for player in self._online.get(tournament_id, {}).values():
            if player.connection_id != exclude:
                player.connection.send_text(payload)
