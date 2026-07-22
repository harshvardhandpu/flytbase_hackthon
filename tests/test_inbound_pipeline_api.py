"""API tests for inbound and pipeline endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── Inbound API Tests ──────────────────────────────────────────────────


def test_inbound_missing_body():
    """422 when no message body is provided."""
    response = client.post(
        "/api/v1/inbound",
        json={"from_email": "test@example.com"},
    )
    assert response.status_code == 422
    detail = response.json().get("detail", "")
    assert "body" in detail.lower() or "field required" in detail.lower()


def test_inbound_invalid_message_id():
    """422 for invalid message_id format in approve."""
    response = client.post(
        "/api/v1/inbound/not-a-uuid/approve",
        json={"approved_by": "bdr@flytbase.com"},
    )
    assert response.status_code == 422


def test_inbound_approve_not_found():
    """404 when message_id doesn't exist."""
    response = client.post(
        f"/api/v1/inbound/{'00000000-0000-0000-0000-000000000000'}/approve",
        json={"approved_by": "bdr@flytbase.com"},
    )
    assert response.status_code == 404


def test_inbound_reject_not_found():
    """404 when message_id doesn't exist for reject."""
    response = client.post(
        f"/api/v1/inbound/{'00000000-0000-0000-0000-000000000000'}/reject",
        json={"rejected_reason": "Too generic"},
    )
    assert response.status_code == 404


# ── Pipeline API Tests ─────────────────────────────────────────────────


def test_pipeline_evaluate_missing_lead():
    """422 when no lead_id is provided."""
    response = client.post(
        "/api/v1/pipeline/evaluate",
        json={},
    )
    assert response.status_code == 422


def test_pipeline_evaluate_invalid_lead():
    """422 for invalid lead_id format."""
    response = client.post(
        "/api/v1/pipeline/evaluate",
        json={"lead_id": "not-a-uuid"},
    )
    assert response.status_code == 422


def test_pipeline_evaluate_not_found():
    """404 when lead_id doesn't exist."""
    response = client.post(
        "/api/v1/pipeline/evaluate",
        json={"lead_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_pipeline_get_evaluation_not_found():
    """404 when task_id doesn't exist."""
    response = client.get(
        f"/api/v1/pipeline/{'00000000-0000-0000-0000-000000000000'}"
    )
    assert response.status_code == 404


def test_pipeline_get_evaluation_invalid_id():
    """422 for invalid task_id format."""
    response = client.get("/api/v1/pipeline/not-a-uuid")
    assert response.status_code == 422


def test_pipeline_advance_missing_stage():
    """404 when lead doesn't exist (check happens before new_stage validation)."""
    response = client.post(
        f"/api/v1/pipeline/{'00000000-0000-0000-0000-000000000000'}/advance",
        json={"reason": "Testing"},
    )
    assert response.status_code == 404


def test_pipeline_advance_not_found():
    """404 when lead_id doesn't exist."""
    response = client.post(
        f"/api/v1/pipeline/{'00000000-0000-0000-0000-000000000000'}/advance",
        json={"new_stage": "qualified", "reason": "Testing", "advanced_by": "tester"},
    )
    assert response.status_code == 404


def test_pipeline_advance_invalid_lead_id():
    """422 for invalid lead_id format."""
    response = client.post(
        "/api/v1/pipeline/not-a-uuid/advance",
        json={"new_stage": "qualified"},
    )
    assert response.status_code == 422


def test_pipeline_list_leads():
    """Returns a list of leads (possibly empty)."""
    response = client.get("/api/v1/pipeline/leads")
    assert response.status_code == 200
    data = response.json()
    assert "leads" in data
    assert isinstance(data["leads"], list)
    assert "total" in data


def test_pipeline_list_leads_with_limit():
    """Respects the limit parameter."""
    response = client.get("/api/v1/pipeline/leads?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["leads"]) <= 10


# ── Schema validation tests ────────────────────────────────────────────


def test_inbound_response_schema():
    """Inbound response should have the expected fields."""
    # We can't easily test a full successful flow without DB,
    # but we can validate the response model schema
    from app.api.router import InboundResponse

    resp = InboundResponse(
        task_id="task-uuid",
        message_id="msg-uuid",
        status="pending_review",
        intent="meeting_request",
        sentiment="positive",
        urgency="high",
        lead_action="update_lead",
        requires_human_approval=True,
        suggested_reply_preview="Hi, thanks",
    )
    assert resp.task_id == "task-uuid"
    assert resp.requires_human_approval is True
    assert resp.status == "pending_review"


def test_pipeline_evaluate_response_schema():
    """Pipeline evaluate response should have expected fields."""
    from app.api.router import PipelineEvaluateResponse

    resp = PipelineEvaluateResponse(
        task_id="task-uuid",
        lead_id="lead-uuid",
        status="completed",
        current_stage="outreach",
        stage_health="stale",
        stagnation_risk="moderate",
        recommended_action={"type": "follow_up"},
    )
    assert resp.status == "completed"
    assert resp.stage_health == "stale"


def test_pipeline_advance_response_schema():
    """Pipeline advance response should have expected fields."""
    from app.api.router import PipelineAdvanceResponse

    resp = PipelineAdvanceResponse(
        lead_id="lead-uuid",
        new_stage="meeting_scheduled",
        previous_stage="outreach",
        status_id="status-uuid",
    )
    assert resp.new_stage == "meeting_scheduled"
    assert resp.previous_stage == "outreach"


def test_inbound_approve_response_schema():
    """Inbound approve response should have expected fields."""
    from app.api.router import InboundApproveResponse

    resp = InboundApproveResponse(
        message_id="msg-uuid",
        status="approved",
    )
    assert resp.status == "approved"
