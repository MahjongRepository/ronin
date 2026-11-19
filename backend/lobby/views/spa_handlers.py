from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.views.assets import render_page

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


async def spa_shell(request: Request) -> Response:
    """
    GET a migrated lobby route - render the shell the lobby app mounts its chrome and the route's view into.
    """
    return render_page(request, template_name="shell.html", context={})
