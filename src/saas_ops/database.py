import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def database_path() -> Path:
    return Path(os.getenv("SAAS_OPS_DB_PATH", "saas_ops.db"))


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(database_path(), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
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
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                target_go_live TEXT NOT NULL,
                contract_value_cents INTEGER NOT NULL CHECK(contract_value_cents >= 0),
                stage TEXT NOT NULL,
                risk TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 0,
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
            CREATE TABLE IF NOT EXISTS schema_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                version INTEGER NOT NULL
            );
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(customers)")}
        if "contract_value_cents" not in columns:
            conn.execute(
                "ALTER TABLE customers ADD COLUMN contract_value_cents INTEGER NOT NULL DEFAULT 0"
            )
            if "contract_value" in columns:
                conn.execute(
                    "UPDATE customers SET contract_value_cents = ROUND(contract_value * 100)"
                )
        if "version" not in columns:
            conn.execute("ALTER TABLE customers ADD COLUMN version INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "INSERT INTO schema_metadata(singleton, version) VALUES (1, 2) "
            "ON CONFLICT(singleton) DO UPDATE SET version = excluded.version"
        )
