from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.monitoring.gauges import BACKUP_STAMP_NAME

if TYPE_CHECKING:
    import sqlite3

_NANOSECONDS_PER_SECOND = 1_000_000_000


def read_backup_stamp(connection: sqlite3.Connection) -> int | None:
    """
    Return the backup stamp's modification time (Unix seconds) from its newest sample, None when the stamp has no sample
    or did not exist at it.
    """
    row = connection.execute(
        'SELECT "exists", modification_time FROM filestat WHERE file LIKE ? ORDER BY timestamp DESC LIMIT 1',
        (f"%{BACKUP_STAMP_NAME}",),
    ).fetchone()
    if row is None or not row[0] or row[1] is None:
        return None

    return row[1] // _NANOSECONDS_PER_SECOND
