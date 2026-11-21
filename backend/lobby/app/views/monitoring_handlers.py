from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from app.monitoring.page import assemble_monitoring_page
from app.monitoring.ranges import DEFAULT_MONITORING_RANGE, MonitoringRange
from app.monitoring.reader import MetricsReader
from app.monitoring.report import monitoring_report
from app.views.error_pages import NO_STORE_HEADERS

if TYPE_CHECKING:
    from starlette.requests import Request


def _selected_range(request: Request) -> MonitoringRange:
    """
    Return the requested range from ``?range=``, the default for a missing or unknown one.
    """
    try:
        return MonitoringRange(request.query_params.get("range", DEFAULT_MONITORING_RANGE))
    except ValueError:
        return DEFAULT_MONITORING_RANGE


async def monitoring_data(request: Request) -> JSONResponse:
    """
    GET /api/lobby/monitoring - the monitoring page's data for ``?range=``: live and started games, and the charts.
    """
    selected = _selected_range(request)
    page = await assemble_monitoring_page(
        selected,
        metrics=MetricsReader(Path(request.app.state.settings.metrics_db_path)),
        game_repo=request.app.state.game_repo,
        game_server=request.app.state.game_server,
    )
    return JSONResponse(monitoring_report(page, selected=selected, with_plots=True), headers=NO_STORE_HEADERS)
