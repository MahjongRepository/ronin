from __future__ import annotations

import time
import unicodedata
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse

from lobby.chat_messages import CHAT_MAX_LENGTH
from lobby.views.assets import render_page
from lobby.views.error_pages import validate_csrf
from lobby.views.settings_handlers import find_account
from shared.dal.models import Tournament

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.tournaments.game_end_poller import TournamentGameEndPoller
    from lobby.tournaments.hub import TournamentHub
    from shared.dal.tournament_repository import TournamentRepository

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


async def create_tournament_and_redirect(request: Request) -> Response:
    """
    POST /tournaments/new - create a tournament owned by the account and redirect to its page.

    A guest has no account to own one and gets a 403; an invalid name gets a 400.
    """
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    if await find_account(request) is None:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    name = _parse_tournament_name(form.get("name"))
    if name is None:
        raise HTTPException(HTTPStatus.BAD_REQUEST)

    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournament = Tournament(id=str(uuid.uuid4()), name=name, owner_user_id=request.user.user_id, created_at=time.time())
    await tournament_repo.create_tournament(tournament)
    return RedirectResponse(f"/tournaments/{tournament.id}", status_code=303)


async def tournament_page(request: Request) -> Response:
    """
    GET /tournaments/{tournament_id} - render the tournament page; its owner also sees the id and the API hints.
    """
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournament = await tournament_repo.get_tournament(request.path_params["tournament_id"])
    if tournament is None:
        raise HTTPException(HTTPStatus.NOT_FOUND)

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    return render_page(
        request,
        template_name="tournament.html",
        context={
            "tournament": tournament,
            "share_url": str(request.url_for("tournament_page", tournament_id=tournament.id)),
            "ws_url": f"{ws_scheme}://{request.url.netloc}/ws/tournaments/{tournament.id}",
            "chat_max_length": CHAT_MAX_LENGTH,
            "tournament_name_max_length": TOURNAMENT_NAME_MAX_LENGTH,
            "is_owner": tournament.owner_user_id == request.user.user_id,
            "username": request.user.username,
        },
    )


async def rename_tournament_and_redirect(request: Request) -> Response:
    """
    POST /tournaments/{tournament_id}/rename - rename the owner's tournament and redirect back to its page.

    Anyone but the owner gets the 404 of an unknown tournament; an invalid name gets a 400.
    """
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    tournament = await _find_owned_tournament(request)
    name = _parse_tournament_name(form.get("name"))
    if name is None:
        raise HTTPException(HTTPStatus.BAD_REQUEST)

    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    await tournament_repo.rename_tournament(tournament.id, name)
    return RedirectResponse(f"/tournaments/{tournament.id}", status_code=303)


async def delete_tournament_and_redirect(request: Request) -> Response:
    """
    POST /tournaments/{tournament_id}/delete - delete the owner's tournament and redirect to the lobby.

    Its open sockets are told ``tournament_deleted`` and closed, and its games are no longer watched for their end;
    games already running keep playing. Anyone but the owner gets the 404 of an unknown tournament.
    """
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    tournament = await _find_owned_tournament(request)
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    await tournament_repo.delete_tournament(tournament.id)

    hub: TournamentHub = request.app.state.tournament_hub
    hub.close_deleted_tournament(tournament.id)
    poller: TournamentGameEndPoller = request.app.state.tournament_game_end_poller
    poller.untrack_tournament(tournament.id)
    return RedirectResponse("/", status_code=303)


async def _find_owned_tournament(request: Request) -> Tournament:
    """
    Return the tournament of the path when the user owns it; raise a 404 for an unknown one or anyone else's.
    """
    tournament_repo: TournamentRepository = request.app.state.tournament_repo
    tournament = await tournament_repo.get_tournament(request.path_params["tournament_id"])
    if tournament is None or tournament.owner_user_id != request.user.user_id:
        raise HTTPException(HTTPStatus.NOT_FOUND)

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
