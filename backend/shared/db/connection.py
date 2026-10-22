import asyncio
import contextlib
import os
import queue
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

_DB_FILE_PERMISSIONS = 0o600

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    api_key_hash TEXT,
    data TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_username
    ON players (username COLLATE NOCASE);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_api_key_hash
    ON players (api_key_hash) WHERE api_key_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS played_games (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_played_games_started_at
    ON played_games (started_at DESC);
"""

_DROPPED_UNRUN = "dropped unrun: the database worker did not drain before shutdown"

type DbOperation[T] = Callable[[sqlite3.Connection], T]
type _Report = Callable[[Any, Exception | None], None]


@dataclass(frozen=True)
class _Job:
    """
    One queued operation, run in a write transaction when `write`; `report` receives its result or error.
    """

    operation: DbOperation[Any]
    write: bool
    report: _Report

    def abandon(self, reason: str) -> None:
        """
        Report the job as abandoned at shutdown: its caller gets the error, or a posted write logs it with its fields.
        """
        self.report(None, RuntimeError(reason))


@dataclass(frozen=True)
class _Stop:
    """
    The close sentinel: the worker closes the connection once every job queued before it has run, then reports.
    """

    report: _Report


class Database:
    """
    The process's SQLite database, owned by one worker thread.

    The thread opens the connection (WAL, schema, file permissions), runs every submitted operation one at a time in
    submission order, and closes it; the event loop never touches SQLite, so a write waiting on another process's lock
    stalls only the queue behind it. A write runs in its own `BEGIN IMMEDIATE` transaction, committed when the operation
    returns and rolled back on any error, so a failure never leaves a transaction open on the connection; a read runs in
    autocommit.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        busy_timeout_ms: int = 5000,
        drain_timeout_seconds: float = 6.0,
    ) -> None:
        if drain_timeout_seconds * 1000 <= busy_timeout_ms:
            raise ValueError("the drain timeout must outlast the busy timeout, so one waiting write can finish")

        self._path = str(path)
        self._busy_timeout_ms = busy_timeout_ms
        self._drain_timeout_seconds = drain_timeout_seconds
        self._jobs: queue.SimpleQueue[_Job | _Stop] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._running: _Job | None = None
        self._abandoned = False
        self._closing = False

    async def open(self) -> None:
        """
        Start the worker thread and wait until it has opened the database; an error opening it is raised here.
        """
        if self._thread is not None or self._closing:
            raise RuntimeError("Database can be opened only once")

        opened = asyncio.get_running_loop().create_future()
        self._thread = threading.Thread(
            target=self._run,
            args=(_future_report(opened),),
            name="sqlite-worker",
            daemon=True,
        )
        self._thread.start()
        try:
            await opened
        except BaseException:
            self._closing = True
            self._jobs.put(_Stop(report=_ignore_report))
            raise

    def submit_read[T](self, operation: DbOperation[T]) -> asyncio.Future[T]:
        """
        Queue a read and return a future for its result; queued at call time, so calls run in call order.
        """
        return self._submit(operation, write=False)

    def submit_write[T](self, operation: DbOperation[T]) -> asyncio.Future[T]:
        """
        Queue a write transaction and return a future for its result or error.
        """
        return self._submit(operation, write=True)

    def post_write(self, operation: DbOperation[object], /, **log_fields: str) -> None:
        """
        Queue a write nobody waits for; its failure, or a post on a database not open, is logged with `log_fields`.
        """
        if not self._is_open:
            logger.error("database write dropped: the database is not open", **log_fields)
            return

        self._jobs.put(_Job(operation=operation, write=True, report=_failure_log(log_fields)))

    async def close(self) -> None:
        """
        Run every queued operation, then close the connection.

        Waits at most `drain_timeout_seconds` for the queue to drain (every queued write can wait out the busy timeout),
        so shutdown never hangs on a stuck write. Past that, every job still queued is dropped and reported (a posted
        write logs its operation and game), the write still running is logged the same way, and the worker closes the
        connection once that write returns.
        """
        was_open = self._is_open
        self._closing = True
        if not was_open:
            return

        closed = asyncio.get_running_loop().create_future()
        stop = _Stop(report=_future_report(closed))
        self._jobs.put(stop)
        drained, _ = await asyncio.wait({closed}, timeout=self._drain_timeout_seconds)
        if not drained:
            self._abandon_queue(stop)

    def _abandon_queue(self, stop: _Stop) -> None:
        """
        Report every job still queued behind a stuck one and the stuck one itself, then queue the close sentinel again.
        """
        logger.error("database worker did not drain before shutdown", timeout_seconds=self._drain_timeout_seconds)
        self._abandoned = True
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                break

            if isinstance(job, _Job):
                job.abandon(_DROPPED_UNRUN)

        running = self._running
        if running is not None:
            running.abandon("still running at shutdown: it may or may not have landed")

        self._jobs.put(stop)

    @property
    def _is_open(self) -> bool:
        return self._thread is not None and not self._closing

    def _submit[T](self, operation: DbOperation[T], *, write: bool) -> asyncio.Future[T]:
        if not self._is_open:
            raise RuntimeError("Database is not open")

        future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        self._jobs.put(_Job(operation=operation, write=write, report=_future_report(future)))
        return future

    def _run(self, report_opened: _Report) -> None:
        """
        The worker thread: open the connection, run jobs until the close sentinel, close the connection.
        """
        try:
            conn = self._connect()
        except Exception as exc:  # noqa: BLE001
            report_opened(None, exc)
            return

        report_opened(None, None)
        try:
            stop = self._run_jobs(conn)
        finally:
            conn.close()

        stop.report(None, None)

    def _run_jobs(self, conn: sqlite3.Connection) -> _Stop:
        while True:
            job = self._jobs.get()
            if isinstance(job, _Stop):
                return job

            self._running = job
            if self._abandoned:
                self._running = None
                job.abandon(_DROPPED_UNRUN)
                continue

            try:
                result = _run_in_transaction(conn, job.operation) if job.write else job.operation(conn)
            except Exception as exc:  # noqa: BLE001
                job.report(None, exc)
            else:
                job.report(result, None)
            finally:
                self._running = None

    def _connect(self) -> sqlite3.Connection:
        """
        Open the database, apply pragmas, create schema, and harden file permissions; close it again on any failure.
        """
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self._path, autocommit=True)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms:d}")
            conn.executescript(_SCHEMA_SQL)
            self._harden_permissions()
        except BaseException:
            conn.close()
            raise

        return conn

    def _harden_permissions(self) -> None:
        """
        Set restrictive file permissions on POSIX systems (best effort).

        Hardens the main DB file and WAL/SHM sibling files created by WAL mode, since they also contain database content
        (password and API-key hashes).
        """
        if os.name != "posix":  # pragma: no cover (platform)
            return

        for suffix in ("", "-wal", "-shm"):
            p = Path(self._path + suffix)
            if p.exists():
                try:
                    p.chmod(_DB_FILE_PERMISSIONS)
                except OSError:
                    logger.warning("could not set file permissions", permissions=oct(_DB_FILE_PERMISSIONS), path=str(p))


def _run_in_transaction[T](conn: sqlite3.Connection, operation: DbOperation[T]) -> T:
    """
    Run a write in its own immediate transaction: commit on return, roll back on any error.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = operation(conn)
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise

    return result


def _future_report(future: asyncio.Future[Any]) -> _Report:
    """
    Build a report that settles `future` on its own loop from the worker thread; dropped once that loop is closed (a
    caller gone with its loop, such as after a drain gave up).
    """
    loop = future.get_loop()

    def settle(result: object, error: Exception | None) -> None:
        if future.done():
            return

        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def report(result: object, error: Exception | None) -> None:
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(settle, result, error)

    return report


def _ignore_report(_result: object, _error: Exception | None) -> None:
    """
    The report of a close nobody waits for (an open that was cancelled).
    """


def _failure_log(log_fields: dict[str, str]) -> _Report:
    """
    Build the report of a posted write: a failure is logged at error level with its fields and traceback.
    """

    def report(_result: object, error: Exception | None) -> None:
        if error is not None:
            logger.error("database write failed", exc_info=error, **log_fields)

    return report
