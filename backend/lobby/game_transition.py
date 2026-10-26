from __future__ import annotations

import asyncio
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
import structlog

from shared.auth.game_ticket import create_signed_ticket

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lobby.occupancy import Occupancy
    from lobby.players import LobbyPlayer
    from lobby.settings import LobbyServerSettings

logger = structlog.get_logger()


class GameStartError(Exception):
    """
    A game start that failed before the game server confirmed the game; ``reason`` is a fixed code for the players.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_PLAYING_LOOKUP_TIMEOUT_SECONDS = 2.0
_START_REQUEST_TIMEOUT = httpx.Timeout(10.0)
_KEEPALIVE_EXPIRY_SECONDS = 2.0
_GAME_SERVER_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=_KEEPALIVE_EXPIRY_SECONDS,
)

_GAME_SERVER_UNAVAILABLE = "game_server_unavailable"
_GAME_SERVER_FULL = "game_server_full"
_GAME_SERVER_ERROR = "game_server_error"
_PLAYER_IN_GAME = "player_in_game"
_INTERNAL_ERROR = "internal_error"
_REFUSAL_REASONS: dict[int, str] = {
    HTTPStatus.CONFLICT: _PLAYER_IN_GAME,
    HTTPStatus.SERVICE_UNAVAILABLE: _GAME_SERVER_FULL,
}


def create_game_server_client(
    game_server_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """
    Build the one client an app calls the game server with.

    Idle pooled connections expire well before uvicorn's default keep-alive timeout, which narrows, but cannot close,
    the window for reusing a connection the server is closing.
    """
    return httpx.AsyncClient(base_url=game_server_url, transport=transport, limits=_GAME_SERVER_LIMITS)


async def start_game(  # noqa: PLR0913
    players: Sequence[LobbyPlayer],
    *,
    num_ai_players: int,
    settings: LobbyServerSettings,
    ticket_secret: str,
    occupancy: Occupancy,
    game_server: httpx.AsyncClient,
) -> str:
    """
    Create a game for the players, then send each of them ``game_starting`` and a 1000 close; return the game id.

    Rooms and matchmaking both start games here, each keeping its own recovery. Every attempt gets a fresh game id: a
    failure may mean the game server created the game anyway (a timeout after the POST arrived), and a retry under the
    same id would collide with that orphan. The same fresh id makes a 409 the occupancy backstop, never a duplicate
    game. The attempt hands the players to the game whatever its outcome, before the caller releases their seats or
    queue places. Before the game server's 201 any failure (a cancellation, which only server shutdown causes, aside) is
    logged and raised as ``GameStartError`` with a fixed reason; the game server's own text goes only to the log. After
    it the game exists with every signed ticket, so delivery only enqueues: a slow player delays nobody else, and one
    whose handler has ended gets nothing (the game server replaces a seat nobody joins with AI).
    """
    game_id = str(uuid.uuid4())
    log = logger.bind(game_id=game_id)
    log.info("game transition starting", players=[player.username for player in players])

    try:
        tickets = [
            create_signed_ticket(
                user_id=player.user_id, username=player.username, room_id=game_id, game_ticket_secret=ticket_secret
            )
            for player in players
        ]
        response = await game_server.post(
            "/games",
            json={
                "game_id": game_id,
                "players": [
                    {"name": player.username, "user_id": player.user_id, "game_ticket": ticket}
                    for player, ticket in zip(players, tickets, strict=True)
                ],
                "num_ai_players": num_ai_players,
            },
            timeout=_START_REQUEST_TIMEOUT,
        )
    except httpx.RequestError as e:
        log.exception("failed to create game")
        raise GameStartError(_GAME_SERVER_UNAVAILABLE) from e
    except Exception as e:
        log.exception("unexpected error creating game")
        raise GameStartError(_INTERNAL_ERROR) from e
    finally:
        occupancy.hand_to_game(player.user_id for player in players)

    if response.status_code != HTTPStatus.CREATED:
        log.error("failed to create game", status=response.status_code, body=response.text)
        raise GameStartError(_REFUSAL_REASONS.get(response.status_code, _GAME_SERVER_ERROR))

    ws_url = f"{settings.game_server_ws_url}/ws/{game_id}"
    for player, ticket in zip(players, tickets, strict=True):
        player.send(
            {
                "type": "game_starting",
                "ws_url": ws_url,
                "game_ticket": ticket,
                "game_id": game_id,
                "game_client_url": settings.game_client_url,
            },
        )
        player.connection.close()

    log.info("game transition complete", ws_url=ws_url)
    return game_id


async def is_user_playing(user_id: str, *, game_server: httpx.AsyncClient) -> bool:
    """
    Ask the game server whether the user is playing a game on it.

    The lookup takes at most ``_PLAYING_LOOKUP_TIMEOUT_SECONDS``. Fail open: a game server that cannot be reached in
    time, or answers anything but 200 or 404, is logged and counted as "not playing", so a game server outage never
    locks users out of rooms and matchmaking.
    """
    try:
        async with asyncio.timeout(_PLAYING_LOOKUP_TIMEOUT_SECONDS):
            response = await game_server.get(f"/players/{quote(user_id, safe='')}")
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
