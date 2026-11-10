from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lobby.players import LobbyPlayer


class TournamentHub:
    """
    The players online on each tournament's page: one connection per user, in memory only.

    Every method is one synchronous step on the event loop, so no lock is needed.
    """

    def __init__(self) -> None:
        self._online: dict[str, dict[str, LobbyPlayer]] = {}

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

    def broadcast(self, tournament_id: str, message: Mapping[str, object], *, exclude: str | None = None) -> None:
        """
        Send a message to every player online in the tournament, encoded once; ``exclude`` skips one connection.
        """
        payload = json.dumps(message)
        for player in self._online.get(tournament_id, {}).values():
            if player.connection_id != exclude:
                player.connection.send_text(payload)
