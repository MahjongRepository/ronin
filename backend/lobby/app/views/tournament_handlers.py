from __future__ import annotations

import time
import unicodedata
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse, RedirectResponse

from app.auth.csrf import is_csrf_valid
from app.chat_messages import CHAT_MAX_LENGTH
from app.dal.models import Tournament, TournamentGameCounts
from app.views.error_pages import NO_STORE_HEADERS, json_csrf_rejection
from app.views.handlers import lobby_websocket_url
from app.views.json_body import parse_json_body

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from app.dal.tournament_repository import TournamentRepository
    from app.tournaments.game_end_poller import TournamentGameEndPoller
    from app.tournaments.hub import TournamentHub

TOURNAMENT_NAME_MAX_LENGTH = 80


def _parse_tournament_name(raw_name: object) -> str | None:
    """
    Return the stripped tournament name, or None when it is empty, too long or holds a control or format character.
    """
    if not isinstance(raw_name, str):
        return None

    name = raw_name.strip()
    if not name or len(name) > TOURNAMENT_NAME_MAX_LENGTH:
        return None

    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in name):
        return None

    return name


def _json_error(code: str, status: HTTPStatus) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers=NO_STORE_HEADERS)


def _tournament_not_found() -> JSONResponse:
    return _json_error("tournament_not_found", HTTPStatus.NOT_FOUND)


async def _read_checked_body(request: Request) -> dict | Response:
    """
    Return the JSON body of a lobby POST, or the answer refusing a malformed body or a failed CSRF check.
    """
    body = await parse_json_body(request)
    if body is None:
        return _json_error("invalid_body", HTTPStatus.BAD_REQUEST)

    if not is_csrf_valid(request):
        return json_csrf_rejection(request)

    return body


async def lobby_tournaments(request: Request) -> JSONResponse:
    """
    GET /api/lobby/tournaments - the user's own tournaments, newest first, and the name limit the create form enforces.
    """
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournaments = await tournament_repo.list_tournaments_by_owner(request.user.user_id)
    counts = await tournament_repo.count_games_by_owner(request.user.user_id)
    no_games = TournamentGameCounts(playing=0, finished=0)
    return JSONResponse(
        {
            "tournaments": [
                {
                    "id": tournament.id,
                    "name": tournament.name,
                    "created_at": tournament.created_at,
                    **counts.get(tournament.id, no_games).model_dump(),
                }
                for tournament in tournaments
            ],
            "name_max_length": TOURNAMENT_NAME_MAX_LENGTH,
        },
        headers=NO_STORE_HEADERS,
    )


async def lobby_create_tournament(request: Request) -> Response:
    """
    POST /api/lobby/tournaments - create a tournament owned by the signed-in account and answer its id.

    A guest has no account to own one and gets a 403 ``guest_account``; an invalid name answers 400 ``invalid_name``.
    """
    body = await _read_checked_body(request)
    if not isinstance(body, dict):
        return body

    if request.user.is_guest:
        return _json_error("guest_account", HTTPStatus.FORBIDDEN)

    name = _parse_tournament_name(body.get("name"))
    if name is None:
        return _json_error("invalid_name", HTTPStatus.BAD_REQUEST)

    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournament = Tournament(id=str(uuid.uuid4()), name=name, owner_user_id=request.user.user_id, created_at=time.time())
    await tournament_repo.create_tournament(tournament)
    return JSONResponse({"tournament_id": tournament.id}, status_code=HTTPStatus.CREATED, headers=NO_STORE_HEADERS)


async def lobby_tournament(request: Request) -> JSONResponse:
    """
    GET /api/lobby/tournaments/{tournament_id} - what the tournament view shows and opens the page's socket with.

    Anyone signed in gets it; ``is_owner`` tells the view whether to show the id, the API hints, rename and delete.
    """
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournament = await tournament_repo.get_tournament(request.path_params["tournament_id"])
    if tournament is None:
        return _tournament_not_found()

    return JSONResponse(
        {
            "name": tournament.name,
            "ws_url": lobby_websocket_url(request, f"/ws/tournaments/{tournament.id}"),
            "chat_max_length": CHAT_MAX_LENGTH,
            "name_max_length": TOURNAMENT_NAME_MAX_LENGTH,
            "is_owner": tournament.owner_user_id == request.user.user_id,
        },
        headers=NO_STORE_HEADERS,
    )


async def lobby_rename_tournament(request: Request) -> Response:
    """
    POST /api/lobby/tournaments/{tournament_id}/rename - rename the owner's tournament and answer the stored name.

    Anyone but the owner gets the 404 of an unknown tournament; an invalid name answers 400 ``invalid_name``.
    """
    body = await _read_checked_body(request)
    if not isinstance(body, dict):
        return body

    tournament = await _find_owned_tournament(request)
    if tournament is None:
        return _tournament_not_found()

    name = _parse_tournament_name(body.get("name"))
    if name is None:
        return _json_error("invalid_name", HTTPStatus.BAD_REQUEST)

    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    await tournament_repo.rename_tournament(tournament.id, name)
    return JSONResponse({"name": name}, headers=NO_STORE_HEADERS)


async def lobby_delete_tournament(request: Request) -> Response:
    """
    POST /api/lobby/tournaments/{tournament_id}/delete - delete the owner's tournament.

    Its open sockets are told ``tournament_deleted`` and closed, and its games are no longer watched for their end;
    games already running keep playing. Anyone but the owner gets the 404 of an unknown tournament.
    """
    body = await _read_checked_body(request)
    if not isinstance(body, dict):
        return body

    tournament = await _find_owned_tournament(request)
    if tournament is None:
        return _tournament_not_found()

    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    await tournament_repo.delete_tournament(tournament.id)

    hub: TournamentHub = request.app.state.tournament_hub
    hub.close_deleted_tournament(tournament.id)
    poller: TournamentGameEndPoller = request.app.state.tournament_game_end_poller
    poller.untrack_tournament(tournament.id)
    return JSONResponse({}, headers=NO_STORE_HEADERS)


async def _find_owned_tournament(request: Request) -> Tournament | None:
    """
    Return the tournament of the path when the user owns it; None for an unknown one or anyone else's.
    """
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournament = await tournament_repo.get_tournament(request.path_params["tournament_id"])
    if tournament is None or tournament.owner_user_id != request.user.user_id:
        return None

    return tournament


async def game_exit_redirect(request: Request) -> Response:
    """
    GET /games/{game_id}/exit - redirect a player leaving a game to its tournament page, or to the lobby otherwise.
    """
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    game = await tournament_repo.get_game(request.path_params["game_id"])
    if game is None:
        return RedirectResponse("/", status_code=303)

    return RedirectResponse(f"/tournaments/{game.tournament_id}", status_code=303)
