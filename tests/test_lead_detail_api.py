"""Tests for lead detail API business_signals schema compatibility."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.router import (
    BusinessSignalResponse,
    LeadDetailResponse,
    _normalize_business_signals,
    get_db,
)
from app.db import models
from app.main import app

# ── Unit: normalization ────────────────────────────────────────────────


class TestNormalizeBusinessSignals:
    def test_legacy_string_list(self) -> None:
        raw = ["hiring robotics engineers", "raised Series B"]
        result = _normalize_business_signals(raw)
        assert len(result) == 2
        assert all(isinstance(s, BusinessSignalResponse) for s in result)
        assert result[0].signal == "hiring robotics engineers"
        assert result[0].url is None
        assert result[1].signal == "raised Series B"

    def test_structured_dict_list(self) -> None:
        raw = [
            {
                "signal": "Autonomous haulage expansion",
                "url": "https://www.bhp.com/news/automation",
                "date": "2026-06-01",
                "category": "automation_investment",
                "source_type": "press_release",
            },
            {
                "signal": "Safety program update",
                "source_url": "https://www.bhp.com/safety",
                "category": "safety_incident",
            },
        ]
        result = _normalize_business_signals(raw)
        assert len(result) == 2
        assert result[0].signal == "Autonomous haulage expansion"
        assert result[0].url == "https://www.bhp.com/news/automation"
        assert result[0].category == "automation_investment"
        assert result[0].source_type == "press_release"
        # source_url mapped to url
        assert result[1].url == "https://www.bhp.com/safety"

    def test_mixed_string_and_dict(self) -> None:
        raw = [
            "legacy string signal",
            {
                "signal": "structured signal",
                "url": "https://news.example.org/item",
                "category": "company_news",
            },
        ]
        result = _normalize_business_signals(raw)
        assert len(result) == 2
        assert result[0].signal == "legacy string signal"
        assert result[1].signal == "structured signal"
        assert result[1].url == "https://news.example.org/item"

    def test_empty_and_invalid(self) -> None:
        assert _normalize_business_signals(None) == []
        assert _normalize_business_signals([]) == []
        assert _normalize_business_signals("not-a-list") == []
        assert _normalize_business_signals([""]) == []


class TestLeadDetailResponseSchema:
    def test_accepts_normalized_string_signals(self) -> None:
        signals = _normalize_business_signals(["hiring", "expansion"])
        model = LeadDetailResponse(
            lead_id=str(uuid.uuid4()),
            company_name="SkyGrid",
            business_signals=signals,
        )
        dumped = model.model_dump()
        assert dumped["business_signals"][0]["signal"] == "hiring"
        assert dumped["business_signals"][1]["signal"] == "expansion"

    def test_accepts_structured_signals(self) -> None:
        signals = _normalize_business_signals(
            [
                {
                    "signal": "AI mining program",
                    "url": "https://www.bhp.com/ai",
                    "date": "2026-01",
                    "category": "technology_announcement",
                    "source_type": "official_website",
                }
            ]
        )
        model = LeadDetailResponse(
            lead_id=str(uuid.uuid4()),
            company_name="BHP",
            business_signals=signals,
        )
        item = model.model_dump()["business_signals"][0]
        assert item["signal"] == "AI mining program"
        assert item["url"] == "https://www.bhp.com/ai"
        assert item["category"] == "technology_announcement"

    def test_rejects_raw_string_list_without_normalize(self) -> None:
        """Raw list[str] must not pass the new schema (documents the regression)."""
        with pytest.raises(ValidationError):
            LeadDetailResponse(
                lead_id=str(uuid.uuid4()),
                business_signals=["raw string not allowed"],  # type: ignore[list-item]
            )


# ── API endpoint (mocked DB) ───────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _build_mock_db(profile_data: dict) -> tuple[MagicMock, uuid.UUID]:
    """Return (mock_db, lead_id) that serves company/lead for get_lead_detail."""
    company_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    company = MagicMock()
    company.id = company_id
    company.name = "BHP"
    company.domain = "bhp.com"
    company.industry = "Mining"
    company.employee_count = 40000
    company.profile_data = profile_data

    lead = MagicMock()
    lead.id = lead_id
    lead.company_id = company_id
    lead.status = "qualified"
    lead.score = 78
    lead.created_at = None

    def query_side_effect(model):  # noqa: ANN001
        q = MagicMock()
        table = getattr(model, "__tablename__", None)
        if table == models.Lead.__tablename__:
            q.filter.return_value.first.return_value = lead
        elif table == models.Company.__tablename__:
            q.filter.return_value.first.return_value = company
        else:
            # PipelineStatus etc.
            q.filter.return_value.first.return_value = None
        return q

    mock_db = MagicMock()
    mock_db.query.side_effect = query_side_effect
    return mock_db, lead_id


class TestGetLeadDetailEndpoint:
    def test_legacy_string_business_signals_return_200(self, client: TestClient) -> None:
        mock_db, lead_id = _build_mock_db(
            {
                "description": "Mining leader",
                "location": "Melbourne",
                "business_signals": [
                    "hiring robotics engineers",
                    "raised Series B",
                ],
                "technology_signals": ["AWS"],
                "pain_points": ["manual inspection"],
                "flytbase_relevance": "High",
            }
        )

        def _override_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_db
        try:
            resp = client.get(f"/api/v1/leads/{lead_id}/detail")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["company_name"] == "BHP"
        assert len(body["business_signals"]) == 2
        assert body["business_signals"][0]["signal"] == "hiring robotics engineers"
        assert body["business_signals"][0]["url"] is None
        assert body["business_signals"][1]["signal"] == "raised Series B"

    def test_structured_business_signals_return_200(self, client: TestClient) -> None:
        mock_db, lead_id = _build_mock_db(
            {
                "description": "Global miner",
                "location": "Melbourne",
                "business_signals": [
                    {
                        "signal": "Autonomous truck fleet expansion",
                        "url": "https://www.bhp.com/automation",
                        "date": "2026-03-01",
                        "category": "automation_investment",
                        "source_type": "press_release",
                    },
                    {
                        "signal": "Safety incident review",
                        "source_url": "https://www.bhp.com/safety",
                        "category": "safety_incident",
                    },
                ],
                "technology_signals": ["autonomous haulage"],
                "pain_points": ["site inspection risk"],
                "flytbase_relevance": "High — drone ops",
            }
        )

        def _override_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_db
        try:
            resp = client.get(f"/api/v1/leads/{lead_id}/detail")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["business_signals"]) == 2
        first = body["business_signals"][0]
        assert first["signal"] == "Autonomous truck fleet expansion"
        assert first["url"] == "https://www.bhp.com/automation"
        assert first["category"] == "automation_investment"
        assert first["source_type"] == "press_release"
        second = body["business_signals"][1]
        assert second["signal"] == "Safety incident review"
        assert second["url"] == "https://www.bhp.com/safety"

    def test_invalid_lead_id_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/leads/not-a-uuid/detail")
        assert resp.status_code == 422
