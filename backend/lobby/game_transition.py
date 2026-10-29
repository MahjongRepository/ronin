from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError

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


class GameLookupError(Exception):
    """
    The game server could not say which game a user is playing; ``str()`` is a fixed description without credentials.
    """


@dataclass(frozen=True)
class GameHandoff:
    """
    What a player needs to reach their seat: the game, its WebSocket URL, their ticket and where the game client lives.

    ``game_starting`` carries it, and the game page's recovery returns it; the ticket stays out of the repr.
    """

    game_id: str
    ws_url: str
    game_ticket: str = field(repr=False)
    game_client_url: str

    def to_game_starting(self) -> dict[str, str]:
        return {"type": "game_starting", **asdict(self)}


class ReplayExportError(Exception):
    """
    The game server could not export a replay; ``str()`` is a fixed description without credentials.
    """


class UnfinishedReplayError(ReplayExportError):
    """
    The replay is a failed game's, which has no game end and so no Tenhou log.
    """


class _LiveSeat(BaseModel):
    game_id: str = Field(min_length=1)
    game_ticket: str = Field(min_length=1)


_PLAYING_LOOKUP_TIMEOUT_SECONDS = 2.0
_WITHDRAW_TIMEOUT_SECONDS = 2.0
_HANDOFF_LOOKUP_TIMEOUT_SECONDS = 2.0
_REPLAY_EXPORT_TIMEOUT_SECONDS = 10.0
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


def _build_handoff(*, game_id: str, game_ticket: str, settings: LobbyServerSettings) -> GameHandoff:
    return GameHandoff(
        game_id=game_id,
        ws_url=f"{settings.game_server_ws_url}/ws/{game_id}",
        game_ticket=game_ticket,
        game_client_url=settings.game_client_url,
    )


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
    same id would collide with that orphan. So a failure without an answer withdraws the id before it is raised, or the
    orphan would hold the players as playing until its pending timeout. The same fresh id makes a 409 the occupancy
    backstop, never a duplicate game. The attempt hands the players to the game whatever its outcome, before the caller
    releases their seats or queue places. Before the game server's 201 any failure (a cancellation, which only server
    shutdown causes, aside) is logged and raised as ``GameStartError`` with a fixed reason; the game server's own text
    goes only to the log. After it the game exists with every signed ticket, so delivery only enqueues: a slow player
    delays nobody else, and one whose handler has ended gets nothing (the game server replaces a seat nobody joins with
    AI).
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
        await _withdraw_game(game_id, settings=settings, game_server=game_server)
        raise GameStartError(_GAME_SERVER_UNAVAILABLE) from e
    except Exception as e:
        log.exception("unexpected error creating game")
        await _withdraw_game(game_id, settings=settings, game_server=game_server)
        raise GameStartError(_INTERNAL_ERROR) from e
    finally:
        occupancy.hand_to_game(player.user_id for player in players)

    if response.status_code != HTTPStatus.CREATED:
        log.error("failed to create game", status=response.status_code, body=response.text)
        raise GameStartError(_REFUSAL_REASONS.get(response.status_code, _GAME_SERVER_ERROR))

    for player, ticket in zip(players, tickets, strict=True):
        handoff = _build_handoff(game_id=game_id, game_ticket=ticket, settings=settings)
        player.send(handoff.to_game_starting())
        player.connection.close()

    log.info("game transition complete")
    return game_id


async def _withdraw_game(game_id: str, *, settings: LobbyServerSettings, game_server: httpx.AsyncClient) -> None:
    """
    Ask the game server to drop a game whose creation went unanswered, whether or not the creation landed.

    Best effort, within ``_WITHDRAW_TIMEOUT_SECONDS``: a failure is logged and leaves an orphan, if any, to its pending
    timeout. The game server keeps a game a player already joined.
    """
    log = logger.bind(game_id=game_id)
    try:
        async with asyncio.timeout(_WITHDRAW_TIMEOUT_SECONDS):
            response = await game_server.delete(
                f"/games/{quote(game_id, safe='')}",
                headers={"Authorization": f"Bearer {settings.internal_api_secret}"},
            )
    except (httpx.HTTPError, TimeoutError) as e:
        log.warning("game withdrawal failed, an orphan holds its players until its pending timeout", error=repr(e))
        return
    except Exception:
        log.exception("unexpected error withdrawing game, an orphan holds its players until its pending timeout")
        return

    if response.status_code == HTTPStatus.UNAUTHORIZED:
        log.error("game server refused the internal API secret: AUTH_INTERNAL_API_SECRET differs between the servers")
        return

    if response.status_code != HTTPStatus.NO_CONTENT:
        log.warning("game server kept the withdrawn game", status=response.status_code)
        return

    log.info("game withdrawn")


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


async def find_game_handoff(
    user_id: str,
    *,
    settings: LobbyServerSettings,
    game_server: httpx.AsyncClient,
) -> GameHandoff | None:
    """
    Recover the handoff of the game the user is playing, with their participant's exact ticket, or None when they play
    none.

    The caller passes only an authenticated user's own id. The game server answers this lookup only for the internal API
    secret, sent as a header so it stays out of every logged URL. It takes at most ``_HANDOFF_LOOKUP_TIMEOUT_SECONDS``
    and, unlike the occupancy lookup, never fails open: a failure raises ``GameLookupError``, so a caller tells "no
    game" apart from "could not ask".
    """
    try:
        async with asyncio.timeout(_HANDOFF_LOOKUP_TIMEOUT_SECONDS):
            response = await game_server.get(
                f"/players/{quote(user_id, safe='')}/game-session",
                headers={"Authorization": f"Bearer {settings.internal_api_secret}"},
            )
    except (httpx.HTTPError, TimeoutError) as e:
        raise GameLookupError(f"request failed: {type(e).__name__}") from e

    if response.status_code == HTTPStatus.NOT_FOUND:
        return None

    if response.status_code == HTTPStatus.UNAUTHORIZED:
        logger.error(
            "game server refused the internal API secret: AUTH_INTERNAL_API_SECRET differs between the servers"
        )
        raise GameLookupError("internal API secret refused")

    if response.status_code != HTTPStatus.OK:
        raise GameLookupError(f"unexpected status {response.status_code}")

    try:
        seat = _LiveSeat.model_validate_json(response.content)
    except ValidationError:
        raise GameLookupError("malformed answer") from None

    return _build_handoff(game_id=seat.game_id, game_ticket=seat.game_ticket, settings=settings)


async def fetch_tenhou_replay(
    game_id: str,
    *,
    settings: LobbyServerSettings,
    game_server: httpx.AsyncClient,
) -> bytes | None:
    """
    Ask the game server to convert a stored replay to tenhou.net XML; None when no such replay is stored.

    The lobby cannot import the converter (it lives with the engine), so the game server converts and answers only the
    internal API secret. It takes at most ``_REPLAY_EXPORT_TIMEOUT_SECONDS`` in all, so the client's shorter per-request
    default is turned off. A failed game's replay raises ``UnfinishedReplayError``, any other failure
    ``ReplayExportError``.
    """
    try:
        async with asyncio.timeout(_REPLAY_EXPORT_TIMEOUT_SECONDS):
            response = await game_server.get(
                f"/replays/{quote(game_id, safe='')}/tenhou",
                headers={"Authorization": f"Bearer {settings.internal_api_secret}"},
                timeout=None,
            )
    except (httpx.HTTPError, TimeoutError) as e:
        raise ReplayExportError(f"request failed: {type(e).__name__}") from e

    if response.status_code == HTTPStatus.NOT_FOUND:
        return None

    if response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
        raise UnfinishedReplayError("replay has no game end")

    if response.status_code != HTTPStatus.OK:
        raise ReplayExportError(f"unexpected status {response.status_code}")

    return response.content


async def hand_back_live_game(
    player: LobbyPlayer,
    *,
    settings: LobbyServerSettings,
    game_server: httpx.AsyncClient,
) -> bool:
    """
    Send a player whose join was refused as ``already_in_game`` the handoff of the game they play, as ``game_starting``,
    and close with 1000; return whether it was sent.

    Both lobby pages follow ``game_starting`` into the game, so this repairs a handoff lost to a closed socket or a
    closed game tab. On False the caller answers ``already_in_game`` as before: the lookup failed, or the game ended
    after the join's own lookup, and the next join attempt sees the current state.
    """
    log = logger.bind(username=player.username)
    try:
        handoff = await find_game_handoff(player.user_id, settings=settings, game_server=game_server)
    except GameLookupError as e:
        log.warning("game handoff lookup failed", error=str(e))
        return False

    if handoff is None:
        log.info("no live game to hand back")
        return False

    player.send(handoff.to_game_starting())
    player.connection.close()
    log.info("live game handed back", game_id=handoff.game_id)
    return True
