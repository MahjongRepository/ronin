import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_LEDGER_SQL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at REAL NOT NULL
);
"""


def migrate(conn: sqlite3.Connection) -> list[str]:
    """
    Apply the migrations the ledger does not list, in name order, in one immediate transaction; return their names.

    The write lock is taken before the ledger is read, so a connection migrating at the same time waits and then finds
    nothing pending. Any failure rolls the whole batch back. ``conn`` must be in autocommit mode.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(_LEDGER_SQL)
        applied = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        pending = [path for path in sorted(MIGRATIONS_DIR.glob("*.sql")) if path.stem not in applied]

        for path in pending:
            conn.executescript(path.read_text())

        applied_at = time.time()
        conn.executemany(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            [(path.stem, applied_at) for path in pending],
        )
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise

    return [path.stem for path in pending]
