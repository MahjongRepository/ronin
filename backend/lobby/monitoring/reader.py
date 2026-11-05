from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

logger = structlog.get_logger()

_BUSY_TIMEOUT_SECONDS = 2.0
_NOT_YET_CREATED_ERRORS = ("no such table", "no such column")


class ReadFailure(StrEnum):
    """
    Why a query over ``metrics.db`` gave no rows to show.

    The collector creates a table when its input first succeeds and a column with the first sample that has it, so a
    missing file, table or column means never collected; any other failure (locked, malformed, corrupt) is unavailable.
    """

    NEVER_COLLECTED = "never_collected"
    UNAVAILABLE = "unavailable"


class MetricsReader:
    """
    Read the collector's ``metrics.db`` read-only, on request, through one short-lived connection per read.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    async def run_each[T](self, queries: Sequence[Callable[[sqlite3.Connection], T]]) -> list[T | ReadFailure]:
        """
        Run each query on one read-only connection in a worker thread, returning its result or why it failed.

        A failed query does not stop the others, so one chart's missing table leaves the rest of the page intact.
        """
        return await asyncio.to_thread(lambda: self._run_each(queries))

    def _run_each[T](self, queries: Sequence[Callable[[sqlite3.Connection], T]]) -> list[T | ReadFailure]:
        if not self._path.exists():
            return [ReadFailure.NEVER_COLLECTED for _ in queries]

        try:
            connection = sqlite3.connect(
                f"{self._path.resolve().as_uri()}?mode=ro", uri=True, timeout=_BUSY_TIMEOUT_SECONDS
            )
        except sqlite3.Error as e:
            logger.warning("metrics database could not be opened", path=str(self._path), error=repr(e))
            return [ReadFailure.UNAVAILABLE for _ in queries]

        with closing(connection):
            return [self._run_one(connection, query) for query in queries]

    def _run_one[T](self, connection: sqlite3.Connection, query: Callable[[sqlite3.Connection], T]) -> T | ReadFailure:
        try:
            return query(connection)
        except sqlite3.Error as e:
            if isinstance(e, sqlite3.OperationalError) and str(e).startswith(_NOT_YET_CREATED_ERRORS):
                return ReadFailure.NEVER_COLLECTED

            logger.warning("metrics database read failed", path=str(self._path), error=repr(e))
            return ReadFailure.UNAVAILABLE
