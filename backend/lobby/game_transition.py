from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
import structlog

from shared.auth.game_ticket import create_signed_ticket

if TYPE_CHECKING:
    from lobby.settings import LobbyServerSettings

logger = structlog.get_logger()


class GameTransitionError(Exception):
    pass


_HTTP_CREATED = HTTPStatus.CREATED
_PLAYING_LOOKUP_TIMEOUT_SECONDS = 2.0


async def create_game_on_server(
    *,
    game_id: str,
    players: list[dict],
    num_ai_players: int,
    settings: LobbyServerSettings,
) -> str:
    """
    Call POST /games on the game server.

    Return the game server WebSocket URL. A ``GameTransitionError`` may mean the game was created anyway (a timeout
    after the request arrived), so a caller must never reuse the game id for another attempt.
    """

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{settings.game_server_url}/games",
                json={
                    "game_id": game_id,
                    "players": players,
                    "num_ai_players": num_ai_players,
                },
            )
            if response.status_code != _HTTP_CREATED:
                raise GameTransitionError(
                    f"Game server returned {response.status_code}: {response.text}",
                )
        except httpx.RequestError as e:
            raise GameTransitionError(f"Failed to connect to game server: {e}") from e

    return f"{settings.game_server_ws_url}/ws/{game_id}"


async def is_user_playing(user_id: str, *, game_server_url: str) -> bool:
    """
    Ask the game server whether the user is playing a game on it.

    The lookup takes at most ``_PLAYING_LOOKUP_TIMEOUT_SECONDS``. Fail open: a game server that cannot be reached in
    time, or answers anything but 200 or 404, is logged and counted as "not playing", so a game server outage never
    locks users out of rooms and matchmaking.
    """

    async with httpx.AsyncClient() as client:
        try:
            async with asyncio.timeout(_PLAYING_LOOKUP_TIMEOUT_SECONDS):
                response = await client.get(f"{game_server_url}/players/{quote(user_id, safe='')}")
        except (httpx.HTTPError, TimeoutError) as e:
            logger.warning("playing lookup failed, treating the user as not playing", error=repr(e))
            return False

    if response.status_code == HTTPStatus.OK:
        return True

    if response.status_code != HTTPStatus.NOT_FOUND:
        logger.warning(
            "playing lookup got an unexpected status, treating the user as not playing", status=response.status_code
        )

    return False


def sign_player_tickets(
    *,
    players: list[tuple[str, str, str]],
    game_id: str,
    ticket_secret: str,
) -> tuple[list[dict], dict[str, str]]:
    """
    Sign game tickets for a list of players.

    Args:
        players: List of (user_id, username, connection_id) tuples.
        game_id: The game ID to include in the ticket.
        ticket_secret: HMAC secret for signing.

    Returns:
        (player_specs, ticket_map) where ticket_map is connection_id -> signed_ticket.
    """
    player_specs = []
    ticket_map: dict[str, str] = {}
    for user_id, username, conn_id in players:
        signed_ticket = create_signed_ticket(
            user_id=user_id, username=username, room_id=game_id, game_ticket_secret=ticket_secret
        )
        player_specs.append({"name": username, "user_id": user_id, "game_ticket": signed_ticket})
        ticket_map[conn_id] = signed_ticket

    return player_specs, ticket_map
