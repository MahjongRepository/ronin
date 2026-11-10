from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lobby.players import LobbyPlayer


class TournamentHub:
    """
    The players online on each tournament's page, one connection per user, and its events subscribers, in memory only.

    A subscriber is keyed by connection, so one user may hold several; it is never online, it only receives what
    ``publish`` sends. Every method is one synchronous step on the event loop, so no lock is needed.
    """

    def __init__(self) -> None:
        self._online: dict[str, dict[str, LobbyPlayer]] = {}
        self._subscribers: dict[str, dict[str, LobbyPlayer]] = {}

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
        Return the connection of the user with this exact username online in the tournament, or None.
        """
        players = self._online.get(tournament_id, {}).values()
        return next((player for player in players if player.username == username), None)

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

    def _send_to_players(self, tournament_id: str, payload: str, *, exclude: str | None) -> None:
        for player in self._online.get(tournament_id, {}).values():
            if player.connection_id != exclude:
                player.connection.send_text(payload)
