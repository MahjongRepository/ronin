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


class GameTransitionError(Exception):
    pass


class GameStartError(Exception):
    """
    A game start that failed before the game server created the game; ``reason`` is the text the players are shown.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_HTTP_CREATED = HTTPStatus.CREATED
_PLAYING_LOOKUP_TIMEOUT_SECONDS = 2.0


async def start_game(
    players: Sequence[LobbyPlayer],
    *,
    num_ai_players: int,
    settings: LobbyServerSettings,
    ticket_secret: str,
    occupancy: Occupancy,
) -> str:
    """
    Create a game for the players, then send each of them ``game_starting`` and a 1000 close; return the game id.

    Rooms and matchmaking both start games here, each keeping its own recovery. Every attempt gets a fresh game id: a
    failure may mean the game server created the game anyway (a timeout after the POST arrived), and a retry under the
    same id would collide with that orphan. The attempt hands the players to the game whatever its outcome, before the
    caller releases their seats or queue places. Before the game server's 201 any exception (a cancellation, which only
    server shutdown causes, aside) is logged and raised as ``GameStartError``. After it the game exists with every
    signed ticket, so delivery only enqueues: a slow player delays nobody else, and one whose handler has ended gets
    nothing (the game server replaces a seat nobody joins with AI).
    """
    game_id = str(uuid.uuid4())
    log = logger.bind(game_id=game_id)
    log.info("game transition starting", players=[player.username for player in players])

    try:
        ws_url, tickets = await _create_game(
            players,
            game_id=game_id,
            num_ai_players=num_ai_players,
            settings=settings,
            ticket_secret=ticket_secret,
        )
    except GameTransitionError as e:
        log.exception("failed to create game")
        raise GameStartError(str(e)) from e
    except Exception as e:
        log.exception("unexpected error creating game")
        raise GameStartError("internal error") from e
    finally:
        occupancy.hand_to_game(player.user_id for player in players)

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


async def _create_game(
    players: Sequence[LobbyPlayer],
    *,
    game_id: str,
    num_ai_players: int,
    settings: LobbyServerSettings,
    ticket_secret: str,
) -> tuple[str, list[str]]:
    """
    Sign a ticket per player and create the game; return the game server URL and the tickets in player order.
    """
    tickets = [
        create_signed_ticket(
            user_id=player.user_id, username=player.username, room_id=game_id, game_ticket_secret=ticket_secret
        )
        for player in players
    ]
    player_specs = [
        {"name": player.username, "user_id": player.user_id, "game_ticket": ticket}
        for player, ticket in zip(players, tickets, strict=True)
    ]
    ws_url = await create_game_on_server(
        game_id=game_id,
        players=player_specs,
        num_ai_players=num_ai_players,
        settings=settings,
    )
    return ws_url, tickets


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
