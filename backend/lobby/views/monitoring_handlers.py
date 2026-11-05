from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.views.assets import render_page

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


async def monitoring_page(request: Request) -> Response:
    """
    GET /admin/monitoring - render the admin monitoring page.
    """
    return render_page(request, template_name="monitoring.html", context={"username": request.user.username})
