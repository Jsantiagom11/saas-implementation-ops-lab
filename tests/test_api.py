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
