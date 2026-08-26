import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saas_ops.database import connection, initialize
from saas_ops.main import app
from saas_ops.models import CustomerCreate, Stage
from saas_ops.service import (
    ConcurrentUpdateError,
    create_customer,
    dashboard,
    list_customers,
    transition,
)


def payload(name: str, value: str = "100.00") -> CustomerCreate:
    return CustomerCreate(
        name=name,
        owner="Jorge Santiago",
        target_go_live=datetime.now(UTC) + timedelta(days=30),
        contract_value=Decimal(value),
    )


def test_same_version_can_transition_only_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "race.db"))
    initialize()
    customer = create_customer(payload("Concurrent account"))

    def advance() -> str:
        try:
            transition(
                customer.id,
                Stage.DATA_VALIDATION,
                "Jorge Santiago",
                "Concurrent approval",
                customer.version,
            )
            return "ok"
        except ConcurrentUpdateError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: advance(), range(2)))

    assert sorted(outcomes) == ["conflict", "ok"]
    current = list_customers()[0]
    assert current.stage == Stage.DATA_VALIDATION
    assert current.version == 1


def test_sqlite_enables_wal_foreign_keys_and_busy_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "pragmas.db"))
    initialize()
    with connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_legacy_money_column_migrates_without_blocking_new_inserts(tmp_path, monkeypatch) -> None:
    database = tmp_path / "legacy.db"
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(database))
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, owner TEXT NOT NULL, target_go_live TEXT NOT NULL,
                contract_value REAL NOT NULL, stage TEXT NOT NULL, risk TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id), actor TEXT NOT NULL,
                action TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """INSERT INTO customers
            (name, owner, target_go_live, contract_value, stage, risk, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("Legacy", "Owner", now, 12.34, "discovery", "low", now, now),
        )

    initialize()
    assert list_customers()[0].contract_value == Decimal("12.34")
    assert create_customer(payload("New account", "0.10")).contract_value == Decimal("0.10")


def test_decimal_contract_totals_are_exact(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "money.db"))
    initialize()
    create_customer(payload("One", "0.10"))
    create_customer(payload("Two", "0.20"))
    assert dashboard().total_contract_value == Decimal("0.30")


def test_index_is_independent_of_process_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "cwd.db"))
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Implementation Control Plane" in response.text


def test_web_output_escapes_api_text_and_sends_expected_version() -> None:
    source = (Path(__file__).parents[1] / "web" / "index.html").read_text()
    assert "${esc(x.name)}" in source
    assert "${esc(x.owner)}" in source
    assert "expected_version" in source
    assert "${x.version}" in source


def test_api_returns_conflict_for_stale_version(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "api-race.db"))
    with TestClient(app) as client:
        created = client.post(
            "/api/customers",
            json={
                "name": "Stale client",
                "owner": "Jorge Santiago",
                "target_go_live": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                "contract_value": "10.00",
            },
        ).json()
        request = {
            "stage": "data_validation",
            "expected_version": created["version"],
            "actor": "Jorge Santiago",
            "note": "Approved",
        }
        first = client.post(f"/api/customers/{created['id']}/transition", json=request)
        assert first.status_code == 200
        stale = client.post(f"/api/customers/{created['id']}/transition", json=request)
    assert stale.status_code == 409
    assert "Stale customer version" in stale.json()["detail"]


@pytest.mark.parametrize("value", ["0.001", "999999999999999.00"])
def test_contract_value_precision_and_range_are_validated(tmp_path, monkeypatch, value) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / f"invalid-{value}.db"))
    with TestClient(app) as client:
        response = client.post(
            "/api/customers",
            json={
                "name": "Invalid money",
                "owner": "Jorge Santiago",
                "target_go_live": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "contract_value": value,
            },
        )
    assert response.status_code == 422
