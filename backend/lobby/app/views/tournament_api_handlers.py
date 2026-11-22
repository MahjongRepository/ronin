from __future__ import annotations

import asyncio
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated

import structlog
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse

from app.dal.models import TournamentGame
from app.game_transition import GameStartError, start_game

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from app.dal.models import Tournament
    from app.dal.tournament_repository import TournamentRepository
    from app.occupancy import Occupancy
    from app.players import LobbyPlayer
    from app.tournaments.game_end_poller import TournamentGameEndPoller
    from app.tournaments.hub import TournamentHub

logger = structlog.get_logger()

MAX_TABLES_PER_START = 40
_TABLE_SIZE = 4
_TOURNAMENT_NOT_FOUND = "tournament_not_found"
_INVALID_GAMES = f"games must be 1 to {MAX_TABLES_PER_START} tables of {_TABLE_SIZE} distinct non-empty usernames"


def _require_distinct(names: list[str]) -> list[str]:
    if len({name.casefold() for name in names}) != len(names):
        msg = "a table names a player twice"
        raise ValueError(msg)

    return names


type _Table = Annotated[
    list[Annotated[str, Field(min_length=1)]],
    Field(min_length=_TABLE_SIZE, max_length=_TABLE_SIZE),
    AfterValidator(_require_distinct),
]


class _StartGamesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    games: list[_Table] = Field(min_length=1, max_length=MAX_TABLES_PER_START)


async def _find_owned_tournament(request: Request) -> Tournament | None:
    """
    Return the tournament in the path when the caller owns it, or None, so an unknown and a foreign one look alike.
    """
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournament = await tournament_repo.get_tournament(request.path_params["tournament_id"])
    if tournament is None or tournament.owner_user_id != request.user.user_id:
        return None

    return tournament


def _not_found() -> JSONResponse:
    return JSONResponse({"error": _TOURNAMENT_NOT_FOUND}, status_code=HTTPStatus.NOT_FOUND)


async def tournament_api(request: Request) -> Response:
    """
    GET /api/tournaments/{tournament_id} - the owner's snapshot: the tournament, who is online and its games.
    """
    tournament = await _find_owned_tournament(request)
    if tournament is None:
        return _not_found()

    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    hub: TournamentHub = request.app.state.tournament_hub
    games = await tournament_repo.list_games(tournament.id)
    return JSONResponse(
        {
            "id": tournament.id,
            "name": tournament.name,
            "online": hub.online_names(tournament.id),
            "games": [game.model_dump(mode="json", exclude={"tournament_id"}) for game in games],
        }
    )


async def start_tournament_games(request: Request) -> Response:
    """
    POST /api/tournaments/{tournament_id}/games - start a game per table, seated East to North in list order.

    Tables start one by one in request order, and each fails alone: its result names why (players not online, players
    in a game, or the game start's reason) and the next table still starts. A malformed body starts nothing.
    """
    tournament = await _find_owned_tournament(request)
    if tournament is None:
        return _not_found()

    try:
        body = _StartGamesRequest.model_validate_json(await request.body())
    except ValidationError:
        return JSONResponse({"error": _INVALID_GAMES}, status_code=HTTPStatus.BAD_REQUEST)

    results = [await _start_table(request, tournament_id=tournament.id, names=names) for names in body.games]
    return JSONResponse({"results": results})


async def _start_table(request: Request, *, tournament_id: str, names: list[str]) -> dict[str, object]:
    """
    Start one table's game and announce it to the tournament; return its result.

    The started players leave the online list at once, so a later table naming one of them finds them offline, and come
    back to it without being announced.
    """
    hub: TournamentHub = request.app.state.tournament_hub
    occupancy: Occupancy = request.app.state.occupancy
    log = logger.bind(tournament_id=tournament_id, players=names)

    found = [hub.find_online(tournament_id, name) for name in names]
    players: list[LobbyPlayer] = [player for player in found if player is not None]
    if len(players) < len(names):
        log.info("tournament table refused, players not online")
        missing = [name for name, player in zip(names, found, strict=True) if player is None]
        return {"error": "players_not_online", "players": missing}

    names = [player.username for player in players]

    async with asyncio.TaskGroup() as group:
        lookups = [group.create_task(occupancy.find_game_conflict(player.user_id)) for player in players]

    busy = [player.username for player, lookup in zip(players, lookups, strict=True) if lookup.result() is not None]
    if busy:
        log.info("tournament table refused, players in a game")
        return {"error": "players_in_game", "players": busy}

    try:
        game_id = await start_game(
            players,
            num_ai_players=0,
            settings=request.app.state.settings,
            ticket_secret=request.app.state.auth_settings.game_ticket_secret,
            occupancy=occupancy,
            game_server=request.app.state.game_server,
            fixed_seats=True,
        )
    except GameStartError as e:
        log.info("tournament table failed to start", reason=e.reason)
        return {"error": e.reason}

    for player in players:
        hub.disconnect(tournament_id, player)

    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    game_end_poller: TournamentGameEndPoller = request.app.state.tournament_game_end_poller
    game = TournamentGame(game_id=game_id, tournament_id=tournament_id, players=names, created_at=time.time())
    await tournament_repo.add_game(game)
    game_end_poller.track(game)
    game_started = {"type": "game_started", "game_id": game_id, "players": names}
    hub.publish(tournament_id, game_started)
    hub.broadcast_presence(tournament_id)
    log.info("tournament game started", game_id=game_id)
    return {"game_id": game_id, "players": names}
