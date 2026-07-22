from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestResearchAPI:
    def test_health_endpoint(self, client: TestClient) -> None:
        """Health endpoint should respond ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_create_research_missing_fields(self, client: TestClient) -> None:
        """Both company_name and domain missing should return 422."""
        response = client.post("/api/v1/research", json={})
        assert response.status_code == 422

    def test_get_task_invalid_uuid(self, client: TestClient) -> None:
        """Non-UUID task_id should return 422."""
        response = client.get("/api/v1/research/not-a-uuid")
        assert response.status_code == 422

    def test_get_report_invalid_uuid(self, client: TestClient) -> None:
        """Non-UUID report_id should return 422."""
        response = client.get("/api/v1/reports/not-a-uuid")
        assert response.status_code == 422
