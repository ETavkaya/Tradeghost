from __future__ import annotations

from fastapi.testclient import TestClient

from tradeghost.apps.api.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"

