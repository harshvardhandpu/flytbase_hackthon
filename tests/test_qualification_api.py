from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestQualificationAPI:
    def test_qualify_missing_fields(self, client: TestClient) -> None:
        """Both report_id and company_name missing should return 422."""
        response = client.post("/api/v1/qualify", json={})
        assert response.status_code == 422

    def test_qualify_invalid_report_id(self, client: TestClient) -> None:
        """Invalid UUID for report_id should return 422."""
        response = client.post(
            "/api/v1/qualify",
            json={"report_id": "not-a-uuid"},
        )
        assert response.status_code == 422

    def test_get_qualification_invalid_uuid(self, client: TestClient) -> None:
        """Non-UUID task_id should return 422."""
        response = client.get("/api/v1/qualification/not-a-uuid")
        assert response.status_code == 422
