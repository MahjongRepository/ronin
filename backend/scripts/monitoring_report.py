import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import structlog

from lobby.game_transition import create_game_server_client
from lobby.monitoring.page import assemble_monitoring_page
from lobby.monitoring.ranges import DEFAULT_MONITORING_RANGE, MonitoringRange
from lobby.monitoring.reader import MetricsReader
from lobby.monitoring.report import monitoring_report
from lobby.settings import LobbyServerSettings
from shared.auth.settings import AuthSettings
from shared.db import Database, SqliteGameRepository


async def main() -> None:
    parser = argparse.ArgumentParser(description="Print the monitoring page's data for a range as one JSON document.")
    parser.add_argument(
        "--range", choices=[choice.value for choice in MonitoringRange], default=DEFAULT_MONITORING_RANGE
    )
    args = parser.parse_args()
    selected = MonitoringRange(args.range)

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
    )
    settings = LobbyServerSettings()
    db = Database(AuthSettings().database_path)
    await db.open()
    game_server = create_game_server_client(settings.game_server_url)

    try:
        page = await assemble_monitoring_page(
            selected,
            metrics=MetricsReader(Path(settings.metrics_db_path)),
            game_repo=SqliteGameRepository(db),
            game_server=game_server,
        )
    finally:
        await game_server.aclose()
        await db.close()

    print(json.dumps(monitoring_report(page, selected=selected), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
