import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def database_path() -> Path:
    return Path(os.getenv("SAAS_OPS_DB_PATH", "saas_ops.db"))


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                target_go_live TEXT NOT NULL,
                contract_value REAL NOT NULL CHECK(contract_value >= 0),
                stage TEXT NOT NULL,
                risk TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_customers_stage ON customers(stage);
            CREATE INDEX IF NOT EXISTS idx_audit_customer ON audit_events(customer_id);
            """
        )

