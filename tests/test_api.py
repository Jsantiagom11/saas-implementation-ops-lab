from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from saas_ops.main import app


def test_customer_lifecycle(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as client:
        created = client.post(
            "/api/customers",
            json={
                "name": "Andes Telecom",
                "owner": "Jorge Santiago",
                "target_go_live": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                "contract_value": 48000,
            },
        )
        assert created.status_code == 201
        customer = created.json()
        assert customer["stage"] == "discovery"

        moved = client.post(
            f"/api/customers/{customer['id']}/transition",
            json={
                "stage": "data_validation",
                "actor": "Jorge Santiago",
                "note": "Discovery signed",
            },
        )
        assert moved.status_code == 200
        assert moved.json()["stage"] == "data_validation"
        assert len(client.get(f"/api/customers/{customer['id']}/audit").json()) == 2


def test_transition_cannot_skip_stage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as client:
        customer = client.post(
            "/api/customers",
            json={"name": "Rumi Wawqi", "owner": "Jorge Santiago",
                  "target_go_live": datetime.now(UTC).isoformat(), "contract_value": 12000},
        ).json()
        response = client.post(
            f"/api/customers/{customer['id']}/transition",
            json={"stage": "go_live", "actor": "Jorge Santiago", "note": "Unsafe shortcut"},
        )
        assert response.status_code == 409


def test_api_rejects_naive_target_timestamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "test.db"))
    with TestClient(app) as client:
        response = client.post(
            "/api/customers",
            json={
                "name": "Naive Clock",
                "owner": "Jorge Santiago",
                "target_go_live": "2026-10-01T12:00:00",
                "contract_value": 100,
            },
        )

    assert response.status_code == 422


def test_dashboard_counts_only_high_risk(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAAS_OPS_DB_PATH", str(tmp_path / "test.db"))
    now = datetime.now(UTC)
    with TestClient(app) as client:
        for name, target in [
            ("High one", now),
            ("High two", now - timedelta(seconds=1)),
            ("Medium one", now + timedelta(hours=1)),
            ("Low one", now + timedelta(days=30)),
        ]:
            response = client.post(
                "/api/customers",
                json={
                    "name": name,
                    "owner": "Jorge Santiago",
                    "target_go_live": target.isoformat(),
                    "contract_value": 100,
                },
            )
            assert response.status_code == 201

        customers = client.get("/api/customers").json()
        metrics = client.get("/api/dashboard").json()

    assert sorted(customer["risk"] for customer in customers) == [
        "high",
        "high",
        "low",
        "medium",
    ]
    assert all("risk_reasons" in customer for customer in customers)
    assert metrics["at_risk"] == 2
