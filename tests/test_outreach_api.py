from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import SessionLocal
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session() -> Session:
    """Provide a database session for test data setup."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _cleanup(db: Session, *records: models.Base) -> None:
    """Delete records in reverse dependency order."""
    for record in records:
        if record is not None:
            db.delete(record)
    db.commit()


def _setup_draft_with_brief(db: Session) -> tuple:
    """Helper to create a company, task, draft, and intelligence brief for testing.

    Returns (company, task, draft, brief).
    """
    company = models.Company(
        id=uuid.uuid4(),
        name="Test Intel Corp",
        domain="testintelcorp.io",
    )
    db.add(company)
    db.flush()

    task = models.AgentTask(
        id=uuid.uuid4(),
        agent_type="outreach",
        status="waiting_for_approval",
        company_id=company.id,
        requires_human_approval=True,
    )
    db.add(task)
    db.flush()

    draft = models.OutreachDraft(
        id=uuid.uuid4(),
        task_id=task.id,
        company_id=company.id,
        status="pending_approval",
        draft_subject="Original Subject",
        draft_body="Original body content.",
        strategy_channel="email",
    )
    db.add(draft)
    db.flush()

    brief = models.CompanyIntelligenceBrief(
        id=uuid.uuid4(),
        outreach_draft_id=draft.id,
        task_id=task.id,
        company_id=company.id,
        brief_data={
            "company_situation_summary": "Original situation summary.",
            "flytbase_fit": {"summary": "Original fit summary."},
            "recommended_sales_angle": "Original sales angle.",
            "detected_business_problems": ["Original problem 1", "Original problem 2"],
            "operational_risks": ["Original risk 1"],
            "growth_signals": ["Signal A"],  # should be preserved when not edited
        },
        source="test",
    )
    db.add(brief)
    db.commit()

    return company, task, draft, brief


class TestOutreachAPI:
    """Original outreach API validation tests."""

    def test_create_outreach_missing_fields(self, client: TestClient) -> None:
        """Both report_id and company_name missing should return 422."""
        response = client.post("/api/v1/outreach", json={})
        assert response.status_code == 422

    def test_create_outreach_invalid_report_id(self, client: TestClient) -> None:
        """Invalid UUID for report_id should return 422."""
        response = client.post(
            "/api/v1/outreach",
            json={"report_id": "not-a-uuid"},
        )
        assert response.status_code == 422

    def test_create_outreach_invalid_qualification_id(self, client: TestClient) -> None:
        """Invalid UUID for qualification_id should return 422."""
        response = client.post(
            "/api/v1/outreach",
            json={
                "company_name": "Test Corp",
                "qualification_id": "not-a-uuid",
            },
        )
        assert response.status_code == 422

    def test_get_outreach_invalid_uuid(self, client: TestClient) -> None:
        """Non-UUID task_id should return 422."""
        response = client.get("/api/v1/outreach/not-a-uuid")
        assert response.status_code == 422

    def test_get_outreach_not_found(self, client: TestClient) -> None:
        """Non-existent task_id should return 404."""
        response = client.get(f"/api/v1/outreach/{'12345678-1234-5678-1234-567812345678'}")
        assert response.status_code == 404

    def test_approve_invalid_draft_id(self, client: TestClient) -> None:
        """Non-UUID draft_id should return 422."""
        response = client.post(
            "/api/v1/outreach/not-a-uuid/approve",
            json={"approved_by": "test@test.com"},
        )
        assert response.status_code == 422

    def test_approve_draft_not_found(self, client: TestClient) -> None:
        """Non-existent draft_id should return 404."""
        response = client.post(
            f"/api/v1/outreach/{'12345678-1234-5678-1234-567812345678'}/approve",
            json={"approved_by": "test@test.com"},
        )
        assert response.status_code == 404

    def test_reject_invalid_draft_id(self, client: TestClient) -> None:
        """Non-UUID draft_id should return 422."""
        response = client.post(
            "/api/v1/outreach/not-a-uuid/reject",
            json={"rejected_reason": "Not a fit"},
        )
        assert response.status_code == 422

    def test_reject_draft_not_found(self, client: TestClient) -> None:
        """Non-existent draft_id should return 404."""
        response = client.post(
            f"/api/v1/outreach/{'12345678-1234-5678-1234-567812345678'}/reject",
            json={"rejected_reason": "Not a fit"},
        )
        assert response.status_code == 404

    def test_get_history_invalid_draft_id(self, client: TestClient) -> None:
        """Non-UUID draft_id should return 422."""
        response = client.get("/api/v1/outreach/not-a-uuid/history")
        assert response.status_code == 422

    def test_get_history_not_found(self, client: TestClient) -> None:
        """Non-existent draft_id should return 404."""
        response = client.get(f"/api/v1/outreach/{'12345678-1234-5678-1234-567812345678'}/history")
        assert response.status_code == 404


class TestOutreachApproveIntelligenceMerge:
    """Tests for the edited_intelligence merge logic in approve_outreach_draft()."""

    def test_approve_without_edited_intelligence(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Approving with no edited_intelligence should leave brief_data unchanged."""
        company, task, draft, brief = _setup_draft_with_brief(db_session)
        original_data = dict(brief.brief_data)
        try:
            response = client.post(
                f"/api/v1/outreach/{draft.id}/approve",
                json={"approved_by": "bdr@test.com"},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "approved"

            db_session.refresh(brief)
            assert brief.brief_data == original_data
            assert brief.brief_data["company_situation_summary"] == "Original situation summary."
            assert brief.brief_data["growth_signals"] == ["Signal A"]
        finally:
            _cleanup(db_session, brief, draft, task, company)

    def test_approve_with_all_intelligence_fields(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Approving with all edited_intelligence fields should update all."""
        company, task, draft, brief = _setup_draft_with_brief(db_session)
        try:
            response = client.post(
                f"/api/v1/outreach/{draft.id}/approve",
                json={
                    "approved_by": "bdr@test.com",
                    "edited_intelligence": {
                        "company_situation_summary": "Edited situation summary.",
                        "flytbase_fit": {"summary": "Edited fit summary."},
                        "recommended_sales_angle": "Edited sales angle.",
                        "detected_business_problems": [
                            "Edited problem 1",
                            "Edited problem 2",
                            "Edited problem 3",
                        ],
                        "operational_risks": ["Edited risk 1", "Edited risk 2"],
                    },
                },
            )
            assert response.status_code == 200

            db_session.refresh(brief)
            assert brief.brief_data["company_situation_summary"] == "Edited situation summary."
            assert brief.brief_data["flytbase_fit"] == {"summary": "Edited fit summary."}
            assert brief.brief_data["recommended_sales_angle"] == "Edited sales angle."
            assert brief.brief_data["detected_business_problems"] == [
                "Edited problem 1",
                "Edited problem 2",
                "Edited problem 3",
            ]
            assert brief.brief_data["operational_risks"] == ["Edited risk 1", "Edited risk 2"]
            # Unedited field should be preserved
            assert brief.brief_data["growth_signals"] == ["Signal A"]
        finally:
            _cleanup(db_session, brief, draft, task, company)

    def test_approve_with_partial_intelligence_merge(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Approving with only some fields should merge, preserving others."""
        company, task, draft, brief = _setup_draft_with_brief(db_session)
        try:
            response = client.post(
                f"/api/v1/outreach/{draft.id}/approve",
                json={
                    "approved_by": "bdr@test.com",
                    "edited_intelligence": {
                        "company_situation_summary": "Partially edited summary.",
                        "detected_business_problems": ["Only edited problem"],
                    },
                },
            )
            assert response.status_code == 200

            db_session.refresh(brief)
            # Edited fields
            assert brief.brief_data["company_situation_summary"] == "Partially edited summary."
            assert brief.brief_data["detected_business_problems"] == ["Only edited problem"]
            # Unedited fields unchanged
            assert brief.brief_data["flytbase_fit"] == {"summary": "Original fit summary."}
            assert brief.brief_data["recommended_sales_angle"] == "Original sales angle."
            assert brief.brief_data["operational_risks"] == ["Original risk 1"]
            assert brief.brief_data["growth_signals"] == ["Signal A"]
        finally:
            _cleanup(db_session, brief, draft, task, company)

    def test_approve_with_empty_edited_intelligence(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Approving with an empty dict should leave brief_data unchanged."""
        company, task, draft, brief = _setup_draft_with_brief(db_session)
        original_data = dict(brief.brief_data)
        try:
            response = client.post(
                f"/api/v1/outreach/{draft.id}/approve",
                json={
                    "approved_by": "bdr@test.com",
                    "edited_intelligence": {},
                },
            )
            assert response.status_code == 200

            db_session.refresh(brief)
            assert brief.brief_data == original_data
        finally:
            _cleanup(db_session, brief, draft, task, company)

    def test_approve_with_edited_intelligence_no_brief(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Approving with edited_intelligence but no existing brief should not crash."""
        # Setup draft WITHOUT a brief
        company = models.Company(
            id=uuid.uuid4(),
            name="No Brief Corp",
            domain="nobrief.io",
        )
        db_session.add(company)
        db_session.flush()

        task = models.AgentTask(
            id=uuid.uuid4(),
            agent_type="outreach",
            status="waiting_for_approval",
            company_id=company.id,
            requires_human_approval=True,
        )
        db_session.add(task)
        db_session.flush()

        draft = models.OutreachDraft(
            id=uuid.uuid4(),
            task_id=task.id,
            company_id=company.id,
            status="pending_approval",
            draft_subject="Subject",
            draft_body="Body.",
            strategy_channel="email",
        )
        db_session.add(draft)
        db_session.commit()

        try:
            response = client.post(
                f"/api/v1/outreach/{draft.id}/approve",
                json={
                    "approved_by": "bdr@test.com",
                    "edited_intelligence": {
                        "company_situation_summary": "Should not crash.",
                    },
                },
            )
            assert response.status_code == 200
            assert response.json()["status"] == "approved"
        finally:
            _cleanup(db_session, draft, task, company)
