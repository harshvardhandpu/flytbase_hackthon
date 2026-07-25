from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.pipeline import _compute_stage_health
from app.agents.registry import build_default_registry
from app.config import get_settings
from app.core.agent_runtime import AgentContext, AgentRuntime
from app.core.contracts import AgentTaskInput
from app.core.task_manager import TaskManager
from app.db import models
from app.db.session import SessionLocal
from app.intelligence.company_resolver import CompanyResolver
from app.providers.manager import ProviderManager
from app.tools import ToolManager, WebContentExtractorTool, WebSearchTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["research"])


# ── request / response schemas ─────────────────────────────────────────


class ResearchRequest(BaseModel):
    company_name: str = ""
    domain: str = ""
    lead_id: str | None = None


class ResearchResponse(BaseModel):
    task_id: str
    status: str
    company_id: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    agent_type: str
    created_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    report_id: str | None = None


class ReportResponse(BaseModel):
    report_id: str
    company_id: str
    company_name: str
    domain: str | None = None
    summary: str
    findings: dict[str, Any]
    sources: list[dict[str, Any]]
    provider: str | None = None
    model: str | None = None
    created_at: str | None = None


# ── dependency injection ────────────────────────────────────────────────


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_runtime(db: Session) -> AgentRuntime:
    settings = get_settings()
    provider = ProviderManager(settings).resolve()
    tools = ToolManager([
        WebSearchTool(),
        WebContentExtractorTool(),
    ])
    tm = TaskManager(db)
    registry = build_default_registry(ai_provider=provider, tool_manager=tools, task_manager=tm)
    return AgentRuntime(registry)


# ── endpoints ───────────────────────────────────────────────────────────


@router.post("/research", response_model=ResearchResponse, status_code=202)
async def create_research_task(
    body: ResearchRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Trigger a research task for a company or domain."""
    if not body.company_name and not body.domain:
        raise HTTPException(status_code=422, detail="Either company_name or domain is required")

    # ── 1. Create or find company ──────────────────────────────────────
    company = None
    if body.domain:
        company = db.query(models.Company).filter(models.Company.domain == body.domain).first()
    if not company and body.company_name:
        company = (
            db.query(models.Company)
            .filter(models.Company.name.ilike(body.company_name))
            .first()
        )

    if not company:
        company = models.Company(
            name=body.company_name or body.domain or "Unknown",
            domain=body.domain,
        )
        db.add(company)
        db.flush()

    # ── 2. Create task and runtime ─────────────────────────────────────
    task_id = uuid.uuid4()
    correlation_id = f"research-{task_id}"
    runtime = build_runtime(db)

    # Get TaskManager from the runtime's dependency chain
    tm = TaskManager(db)

    task_input = AgentTaskInput(
        id=task_id,
        agent_type="research",
        input_data={"company_name": body.company_name, "domain": body.domain or company.domain},
        company_id=company.id,
    )

    # ── 3. Execute with lifecycle ──────────────────────────────────────
    db_task = tm.create_task(task_input)
    tm.mark_running(db_task.id)

    context = AgentContext(task_id=task_id, correlation_id=correlation_id)

    try:
        result = await runtime.execute(context, task_input)

        # ── 4. Persist ResearchReport ──────────────────────────────────
        findings = result.output_data.get("findings", {})
        report = models.ResearchReport(
            id=uuid.uuid4(),
            company_id=company.id,
            task_id=task_id,
            summary=result.summary,
            findings=findings,
            sources=[{"url": s} for s in findings.get("sources", [])],
            provider=result.output_data.get("providers_used"),
        )
        db.add(report)

        # Update company profile
        if findings.get("industry"):
            company.industry = findings["industry"]
        if findings.get("employee_count"):
            company.employee_count = findings["employee_count"]
        company.profile_data = findings

        tm.mark_completed(task_id, result.output_data)
        db.commit()

        return ResearchResponse(
            task_id=str(task_id),
            status="completed",
            company_id=str(company.id),
        ).model_dump()

    except Exception as exc:
        db.rollback()
        try:
            tm.mark_failed(task_id, str(exc))
            db.commit()
        except Exception:
            pass

        raise HTTPException(status_code=500, detail=f"Research execution failed: {exc}")


@router.get("/research/{task_id}", response_model=TaskStatusResponse)
async def get_research_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Poll the status of a research task."""
    try:
        uid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")

    task = db.query(models.AgentTask).filter(models.AgentTask.id == uid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    report_id = None
    if task.reports:
        report_id = str(task.reports[0].id)

    return TaskStatusResponse(
        task_id=str(task.id),
        status=task.status,
        agent_type=task.agent_type,
        created_at=task.created_at.isoformat() if task.created_at else None,
        completed_at=task.updated_at.isoformat()
        if task.status == "completed" and task.updated_at
        else None,
        error_message=task.error_message,
        report_id=report_id,
    ).model_dump()


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_research_report(
    report_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get the full research report."""
    try:
        uid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid report_id format")

    report = db.query(models.ResearchReport).filter(models.ResearchReport.id == uid).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    company = db.query(models.Company).filter(models.Company.id == report.company_id).first()

    return ReportResponse(
        report_id=str(report.id),
        company_id=str(report.company_id),
        company_name=company.name if company else "Unknown",
        domain=company.domain if company else None,
        summary=report.summary,
        findings=report.findings,
        sources=report.sources,
        provider=report.provider,
        model=report.model,
        created_at=report.created_at.isoformat() if report.created_at else None,
    ).model_dump()


# ── Qualification endpoints ─────────────────────────────────────────────


class QualifyRequest(BaseModel):
    report_id: str = ""
    company_name: str = ""
    domain: str = ""
    lead_id: str | None = None
    icp_config: dict[str, Any] | None = None


class QualifyResponse(BaseModel):
    task_id: str
    status: str
    score: int | None = None
    priority: str | None = None
    qualification_id: str | None = None


class QualificationStatusResponse(BaseModel):
    task_id: str
    status: str
    agent_type: str
    score: int | None = None
    priority: str | None = None
    icp_match_score: int | None = None
    buying_signal_score: int | None = None
    company_fit_score: int | None = None
    reasons: list[str] = []
    risks: list[str] = []
    reasoning: str = ""
    recommended_urgency: str | None = None
    recommended_sales_angle: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


@router.post("/qualify", response_model=QualifyResponse, status_code=202)
async def create_qualification_task(
    body: QualifyRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Trigger a qualification task for a researched company."""
    if not body.report_id and not body.company_name:
        raise HTTPException(
            status_code=422,
            detail="Either report_id or company_name is required",
        )

    # ── 1. Resolve company and research report ─────────────────────────
    company = None
    findings: dict[str, Any] = {}
    report = None

    if body.report_id:
        try:
            report_uid = uuid.UUID(body.report_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid report_id format")
        report = db.query(models.ResearchReport).filter(
            models.ResearchReport.id == report_uid
        ).first()
        if report:
            findings = report.findings or {}
            company = db.query(models.Company).filter(
                models.Company.id == report.company_id
            ).first()

    if not company and body.company_name:
        company = db.query(models.Company).filter(
            models.Company.name.ilike(body.company_name)
        ).first()

    if not company and body.domain:
        company = db.query(models.Company).filter(
            models.Company.domain == body.domain
        ).first()

    if not company:
        company = models.Company(
            name=body.company_name or body.domain or "Unknown",
            domain=body.domain,
        )
        db.add(company)
        db.flush()

    # ── 2. Create task and runtime ────────────────────────────────────
    task_id = uuid.uuid4()
    correlation_id = f"qualification-{task_id}"
    runtime = build_runtime(db)
    tm = TaskManager(db)

    task_input = AgentTaskInput(
        id=task_id,
        agent_type="qualification",
        input_data={
            "report_id": body.report_id,
            "company_name": company.name,
            "findings": findings,
            "icp_config": body.icp_config,
        },
        company_id=company.id,
        lead_id=uuid.UUID(body.lead_id) if body.lead_id else None,
    )

    # ── 3. Execute with lifecycle ─────────────────────────────────────
    db_task = tm.create_task(task_input)
    tm.mark_running(db_task.id)
    context = AgentContext(task_id=task_id, correlation_id=correlation_id)

    try:
        result = await runtime.execute(context, task_input)
        output = result.output_data

        # ── 4. Persist QualificationResult ────────────────────────────
        qual = models.QualificationResult(
            id=uuid.uuid4(),
            task_id=task_id,
            company_id=company.id,
            lead_id=uuid.UUID(body.lead_id) if body.lead_id else None,
            report_id=uuid.UUID(body.report_id) if body.report_id else None,
            icp_config_id=None,
            overall_score=output.get("overall_score", 0),
            icp_match_score=output.get("icp_match_score", 0),
            pain_alignment_score=output.get("pain_alignment_score", 0),
            buying_signal_score=output.get("buying_signal_score", 0),
            company_fit_score=output.get("company_fit_score", 0),
            priority=output.get("priority", "COLD"),
            reasoning=output.get("reasoning", ""),
            reasons=output.get("reasons", []),
            risks=output.get("risks", []),
            evidence_based_reasons=output.get("evidence_based_reasons", []),
            qualification_summary=output.get("qualification_summary", ""),
            recommended_urgency=output.get("recommended_bdr_action", {}).get("urgency"),
            recommended_sales_angle=output.get("recommended_bdr_action", {}).get(
                "suggested_sales_angle"
            ),
            icp_inline_config=output.get("icp_config_used"),
            provider=output.get("providers_used"),
        )
        db.add(qual)

        # Update lead score if lead_id provided
        if body.lead_id:
            lead = db.query(models.Lead).filter(
                models.Lead.id == uuid.UUID(body.lead_id)
            ).first()
            if lead:
                lead.score = output.get("overall_score")
                lead.score_reasoning = output.get("reasoning", "")

        tm.mark_completed(task_id, output)
        db.commit()

        return QualifyResponse(
            task_id=str(task_id),
            status="completed",
            score=output.get("overall_score"),
            priority=output.get("priority"),
            qualification_id=str(qual.id),
        ).model_dump()

    except Exception as exc:
        db.rollback()
        try:
            tm.mark_failed(task_id, str(exc))
            db.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail=f"Qualification execution failed: {exc}"
        )


@router.get("/qualification/{task_id}", response_model=QualificationStatusResponse)
async def get_qualification_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Poll the status and result of a qualification task."""
    try:
        uid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")

    task = db.query(models.AgentTask).filter(models.AgentTask.id == uid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Find qualification result
    qual = db.query(models.QualificationResult).filter(
        models.QualificationResult.task_id == uid
    ).first()

    return QualificationStatusResponse(
        task_id=str(task.id),
        status=task.status,
        agent_type=task.agent_type,
        score=qual.overall_score if qual else None,
        priority=qual.priority if qual else None,
        icp_match_score=qual.icp_match_score if qual else None,
        buying_signal_score=qual.buying_signal_score if qual else None,
        company_fit_score=qual.company_fit_score if qual else None,
        reasons=qual.reasons if qual else [],
        risks=qual.risks if qual else [],
        reasoning=qual.reasoning if qual else "",
        recommended_urgency=qual.recommended_urgency if qual else None,
        recommended_sales_angle=qual.recommended_sales_angle if qual else None,
        created_at=task.created_at.isoformat() if task.created_at else None,
        completed_at=task.updated_at.isoformat()
        if task.status == "completed" and task.updated_at
        else None,
        error_message=task.error_message,
    ).model_dump()


# ── Outreach endpoints ─────────────────────────────────────────────────


class OutreachRequest(BaseModel):
    company_name: str = ""
    domain: str = ""
    report_id: str = ""
    qualification_id: str = ""
    lead_id: str | None = None


class OutreachResponse(BaseModel):
    task_id: str
    status: str
    draft_id: str | None = None


class OutreachStatusResponse(BaseModel):
    task_id: str
    status: str
    agent_type: str
    draft_id: str | None = None
    company_name: str = ""
    outreach_strategy: dict[str, Any] = {}
    personalization: dict[str, Any] = {}
    email_draft: dict[str, Any] = {}
    company_intelligence: dict[str, Any] = {}
    approval_summary: dict[str, Any] = {}
    created_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


class ApproveRequest(BaseModel):
    approved_by: str = ""
    approval_notes: str = ""
    edited_subject: str | None = None
    edited_body: str | None = None
    edited_intelligence: dict[str, Any] | None = None


class ApproveResponse(BaseModel):
    draft_id: str
    status: str
    history_id: str | None = None


class RejectRequest(BaseModel):
    rejected_reason: str = ""


class RejectResponse(BaseModel):
    draft_id: str
    status: str


class OutreachHistoryResponse(BaseModel):
    draft_id: str
    history: list[dict[str, Any]] = []


@router.post("/outreach", response_model=OutreachResponse, status_code=202)
async def create_outreach_task(
    body: OutreachRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate an outreach draft from research and/or qualification context."""
    if not body.report_id and not body.company_name:
        raise HTTPException(
            status_code=422,
            detail="Either report_id or company_name is required",
        )

    # ── 1. Resolve company, research, and qualification ────────────────
    company = None
    research_findings: dict[str, Any] = {}
    qualification: dict[str, Any] = {}
    report = None
    qual = None

    if body.report_id:
        try:
            report_uid = uuid.UUID(body.report_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid report_id format")
        report = db.query(models.ResearchReport).filter(
            models.ResearchReport.id == report_uid
        ).first()
        if report:
            research_findings = report.findings or {}
            company = db.query(models.Company).filter(
                models.Company.id == report.company_id
            ).first()

    if body.qualification_id:
        try:
            qual_uid = uuid.UUID(body.qualification_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid qualification_id format")
        qual = db.query(models.QualificationResult).filter(
            models.QualificationResult.id == qual_uid
        ).first()
        if qual:
            qualification = {
                "overall_score": qual.overall_score,
                "icp_match_score": qual.icp_match_score,
                "buying_signal_score": qual.buying_signal_score,
                "company_fit_score": qual.company_fit_score,
                "priority": qual.priority,
                "reasoning": qual.reasoning,
                "reasons": qual.reasons,
                "risks": qual.risks,
                "recommended_bdr_action": {
                    "urgency": qual.recommended_urgency,
                    "suggested_sales_angle": qual.recommended_sales_angle,
                },
            }

    if not company and body.company_name:
        company = db.query(models.Company).filter(
            models.Company.name.ilike(body.company_name)
        ).first()

    if not company and body.domain:
        company = db.query(models.Company).filter(
            models.Company.domain == body.domain
        ).first()

    if not company:
        company = models.Company(
            name=body.company_name or body.domain or "Unknown",
            domain=body.domain,
        )
        db.add(company)
        db.flush()

    # ── 2. Create task and runtime ────────────────────────────────────
    task_id = uuid.uuid4()
    correlation_id = f"outreach-{task_id}"
    runtime = build_runtime(db)
    tm = TaskManager(db)

    task_input = AgentTaskInput(
        id=task_id,
        agent_type="outreach",
        input_data={
            "company_name": company.name,
            "research_findings": research_findings,
            "qualification": qualification,
        },
        company_id=company.id,
        lead_id=uuid.UUID(body.lead_id) if body.lead_id else None,
        requires_human_approval=True,
    )

    # ── 3. Execute with lifecycle ─────────────────────────────────────
    db_task = tm.create_task(task_input)
    tm.mark_running(db_task.id)
    context = AgentContext(task_id=task_id, correlation_id=correlation_id)

    try:
        result = await runtime.execute(context, task_input)
        output = result.output_data

        # ── 4. Persist OutreachDraft ──────────────────────────────────
        strategy = output.get("outreach_strategy", {})
        persona = output.get("personalization", {})
        email = output.get("email_draft", {})

        draft = models.OutreachDraft(
            id=uuid.uuid4(),
            task_id=task_id,
            company_id=company.id,
            lead_id=uuid.UUID(body.lead_id) if body.lead_id else None,
            report_id=uuid.UUID(body.report_id) if body.report_id else None,
            qualification_id=uuid.UUID(body.qualification_id)
            if body.qualification_id
            else None,
            strategy_channel=strategy.get("recommended_channel", "email"),
            strategy_urgency=strategy.get("urgency", "This week"),
            strategy_reasoning=strategy.get("reasoning", ""),
            company_hook=persona.get("company_hook", ""),
            detected_pain_point=persona.get("detected_pain_point", ""),
            flytbase_value_proposition=persona.get("flytbase_value_proposition", ""),
            draft_subject=email.get("subject", ""),
            draft_body=email.get("body", ""),
            follow_up_suggestion=email.get("follow_up_suggestion", ""),
            status="pending_approval",
            provider=output.get("providers_used"),
        )
        db.add(draft)
        db.flush()

        intelligence_brief = models.CompanyIntelligenceBrief(
            id=uuid.uuid4(),
            outreach_draft_id=draft.id,
            task_id=task_id,
            company_id=company.id,
            report_id=report.id if report else None,
            qualification_id=qual.id if qual else None,
            brief_data=output.get("company_intelligence", {}),
            source=output.get("company_intelligence", {}).get(
                "source", "simulated_structured_intelligence"
            ),
        )
        db.add(intelligence_brief)

        # Mark task as waiting_for_approval (not completed — needs human review)
        tm.mark_waiting_for_approval(task_id)
        db.commit()

        return OutreachResponse(
            task_id=str(task_id),
            status="pending_approval",
            draft_id=str(draft.id),
        ).model_dump()

    except Exception as exc:
        db.rollback()
        try:
            tm.mark_failed(task_id, str(exc))
            db.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail=f"Outreach execution failed: {exc}"
        )


@router.get("/outreach/{task_id}", response_model=OutreachStatusResponse)
async def get_outreach_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve the full outreach draft including strategy, personalization, and email."""
    try:
        uid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")

    task = db.query(models.AgentTask).filter(models.AgentTask.id == uid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    draft = db.query(models.OutreachDraft).filter(
        models.OutreachDraft.task_id == uid
    ).first()
    intelligence_brief = None
    if draft:
        intelligence_brief = db.query(models.CompanyIntelligenceBrief).filter(
            models.CompanyIntelligenceBrief.outreach_draft_id == draft.id
        ).first()

    company_name = ""
    if draft and draft.company_id:
        company = db.query(models.Company).filter(
            models.Company.id == draft.company_id
        ).first()
        if company:
            company_name = company.name

    return OutreachStatusResponse(
        task_id=str(task.id),
        status=task.status,
        agent_type=task.agent_type,
        draft_id=str(draft.id) if draft else None,
        company_name=company_name,
        outreach_strategy={
            "recommended_channel": draft.strategy_channel if draft else "",
            "urgency": draft.strategy_urgency if draft else "",
            "reasoning": draft.strategy_reasoning if draft else "",
        } if draft else {},
        personalization={
            "company_hook": draft.company_hook if draft else "",
            "detected_pain_point": draft.detected_pain_point if draft else "",
            "flytbase_value_proposition": draft.flytbase_value_proposition if draft else "",
        } if draft else {},
        email_draft={
            "subject": draft.draft_subject if draft else "",
            "body": draft.draft_body if draft else "",
            "follow_up_suggestion": draft.follow_up_suggestion if draft else "",
        } if draft else {},
        company_intelligence=intelligence_brief.brief_data if intelligence_brief else {},
        approval_summary={
            "status": draft.status if draft else "",
            "approved_by": draft.approved_by if draft else None,
            "approved_at": draft.approved_at.isoformat()
            if draft and draft.approved_at
            else None,
            "rejected_reason": draft.rejected_reason if draft else None,
        } if draft else {},
        created_at=task.created_at.isoformat() if task.created_at else None,
        completed_at=task.updated_at.isoformat()
        if task.status in ("completed", "waiting_for_approval") and task.updated_at
        else None,
        error_message=task.error_message,
    ).model_dump()


@router.post("/outreach/{draft_id}/approve", response_model=ApproveResponse)
async def approve_outreach_draft(
    draft_id: str,
    body: ApproveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Approve an outreach draft. Does NOT auto-send — only marks as approved."""
    try:
        uid = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid draft_id format")

    draft = db.query(models.OutreachDraft).filter(
        models.OutreachDraft.id == uid
    ).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft.status = "approved"
    draft.approved_by = body.approved_by or "unknown"
    draft.approval_notes = body.approval_notes

    draft.approved_at = datetime.now(timezone.utc)

    # If the BDR edited the draft before approval, persist the edits
    if body.edited_subject is not None:
        draft.draft_subject = body.edited_subject
    if body.edited_body is not None:
        draft.draft_body = body.edited_body

    # If the BDR edited the intelligence sections, persist those too
    if body.edited_intelligence is not None:
        brief = db.query(models.CompanyIntelligenceBrief).filter(
            models.CompanyIntelligenceBrief.outreach_draft_id == draft.id
        ).first()
        if brief:
            current = dict(brief.brief_data or {})
            intel = body.edited_intelligence

            # Merge text fields
            if "company_situation_summary" in intel:
                current["company_situation_summary"] = intel["company_situation_summary"]
            if "flytbase_fit" in intel:
                current["flytbase_fit"] = intel["flytbase_fit"]
            if "recommended_sales_angle" in intel:
                current["recommended_sales_angle"] = intel["recommended_sales_angle"]
            if "detected_business_problems" in intel:
                current["detected_business_problems"] = intel["detected_business_problems"]
            if "operational_risks" in intel:
                current["operational_risks"] = intel["operational_risks"]

            brief.brief_data = current

    # Create immutable history record (captures what was actually approved)
    history = models.OutreachHistory(
        id=uuid.uuid4(),
        draft_id=draft.id,
        company_id=draft.company_id,
        lead_id=draft.lead_id,
        sent_subject=draft.draft_subject,
        sent_body=draft.draft_body,
        channel=draft.strategy_channel,
        action="draft_approved",
        approved_by=body.approved_by or "unknown",
        approved_at=draft.approved_at,
    )
    db.add(history)

    # Also mark the agent task as completed
    task = db.query(models.AgentTask).filter(
        models.AgentTask.id == draft.task_id
    ).first()
    if task:
        task.status = "completed"

    db.commit()

    return ApproveResponse(
        draft_id=str(draft.id),
        status="approved",
        history_id=str(history.id),
    ).model_dump()


@router.post("/outreach/{draft_id}/reject", response_model=RejectResponse)
async def reject_outreach_draft(
    draft_id: str,
    body: RejectRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reject an outreach draft with a reason."""
    try:
        uid = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid draft_id format")

    draft = db.query(models.OutreachDraft).filter(
        models.OutreachDraft.id == uid
    ).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft.status = "rejected"
    draft.rejected_reason = body.rejected_reason

    # Mark the agent task as completed (rejected)
    task = db.query(models.AgentTask).filter(
        models.AgentTask.id == draft.task_id
    ).first()
    if task:
        task.status = "completed"

    db.commit()

    return RejectResponse(
        draft_id=str(draft.id),
        status="rejected",
    ).model_dump()


@router.get("/outreach/{draft_id}/history", response_model=OutreachHistoryResponse)
async def get_outreach_history(
    draft_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve the approval/send history for an outreach draft."""
    try:
        uid = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid draft_id format")

    draft = db.query(models.OutreachDraft).filter(
        models.OutreachDraft.id == uid
    ).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    history_records = db.query(models.OutreachHistory).filter(
        models.OutreachHistory.draft_id == uid
    ).order_by(models.OutreachHistory.created_at.asc()).all()

    return OutreachHistoryResponse(
        draft_id=str(draft.id),
        history=[
            {
                "id": str(h.id),
                "action": h.action,
                "channel": h.channel,
                "sent_subject": h.sent_subject,
                "sent_body": h.sent_body[:500] if h.sent_body else "",
                "approved_by": h.approved_by,
                "approved_at": h.approved_at.isoformat()
                if h.approved_at
                else None,
                "response_received": h.response_received,
            }
            for h in history_records
        ],
    ).model_dump()


# ── Inbound endpoints ──────────────────────────────────────────────────


class InboundRequest(BaseModel):
    from_email: str = ""
    from_name: str = ""
    subject: str = ""
    body: str = ""
    channel: str = "email"
    lead_id: str | None = None
    contact_id: str | None = None
    company_id: str | None = None


class ManualInboundSimulationRequest(BaseModel):
    sender_name: str
    company_name: str
    sender_email: str
    message_content: str


class InboundResponse(BaseModel):
    task_id: str
    message_id: str | None = None
    status: str
    intent: str | None = None
    sentiment: str | None = None
    urgency: str | None = None
    lead_action: str | None = None
    requires_human_approval: bool = False
    suggested_reply_preview: str = ""


class InboundAnalysisResponse(BaseModel):
    task_id: str
    status: str
    agent_type: str
    message: dict[str, Any] = {}
    message_id: str | None = None
    analysis: dict[str, Any] = {}
    lead_action: dict[str, Any] = {}
    suggested_reply: dict[str, Any] = {}
    approval_summary: dict[str, Any] = {}
    created_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


class InboundApproveRequest(BaseModel):
    approved_by: str = ""
    approval_notes: str = ""


class InboundApproveResponse(BaseModel):
    message_id: str
    status: str


class InboundRejectRequest(BaseModel):
    rejected_reason: str = ""


class InboundRejectResponse(BaseModel):
    message_id: str
    status: str


def _find_or_create_simulation_lead(
    db: Session, company_name: str, sender_name: str, sender_email: str,
    domain: str | None = None,
) -> tuple[models.Company, models.Contact, models.Lead]:
    """Resolve the existing demo lead or create the minimum inbound records.

    If ``domain`` is provided (from CompanyResolver), it is set on the
    Company record to enable downstream domain-based lookups by the
    ResearchAgent.
    """
    created = False
    # Try to find by domain first (most reliable), then by email domain, then by name
    company = None
    if domain:
        company = db.query(models.Company).filter(models.Company.domain == domain).first()
    if not company:
        company = db.query(models.Company).filter(
            models.Company.name.ilike(f"%{company_name}%")
        ).first()
    if not company:
        company = models.Company(
            name=company_name,
            domain=domain,
            profile_data={"source": "manual_inbound"},
        )
        db.add(company)
        db.flush()
        created = True
    elif domain and not company.domain:
        # Update existing company with resolved domain
        company.domain = domain
        db.flush()
        created = True

    contact = db.query(models.Contact).filter(models.Contact.email == sender_email).first()
    if not contact:
        first_name, *remaining_names = sender_name.strip().split(maxsplit=1)
        contact = models.Contact(
            company_id=company.id,
            first_name=first_name or None,
            last_name=remaining_names[0] if remaining_names else None,
            email=sender_email,
        )
        db.add(contact)
        db.flush()
        created = True

    lead = db.query(models.Lead).filter(
        models.Lead.company_id == company.id, models.Lead.contact_id == contact.id
    ).first()
    if not lead:
        lead = models.Lead(
            company_id=company.id,
            contact_id=contact.id,
            status="new",
            source="manual_inbound",
        )
        db.add(lead)
        db.flush()

        stage = db.query(models.PipelineStage).filter(models.PipelineStage.name == "new").first()
        if stage:
            db.add(models.PipelineStatus(lead_id=lead.id, stage=stage.name, is_current=True))
        created = True

    if created:
        db.commit()
    return company, contact, lead


def _simulation_recommendation_text(
    recommended_action: dict[str, Any] | None,
    follow_up_suggestion: str | None,
) -> str:
    """Prefer human-readable pipeline action text over raw action type labels."""
    action = recommended_action or {}
    return (
        action.get("action")
        or action.get("description")
        or action.get("reasoning")
        or follow_up_suggestion
        or "Review the inbound message and schedule a discovery call."
    )


@router.post("/inbound/simulate")
async def simulate_inbound_email(
    body: ManualInboundSimulationRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Run a manually entered email through inbound, qualification, and pipeline agents.

    Enrichment pipeline:
    1. Extract email domain and resolve company intelligence
    2. Create/find company, contact, and lead
    3. Enrich company profile with resolver data
    4. Process inbound message (intent/sentiment analysis)
    5. Run research enrichment automatically (if no existing report)
    6. Qualify the lead using research + email context
    7. Evaluate pipeline position
    """
    values = (
        body.sender_name.strip(),
        body.company_name.strip(),
        body.sender_email.strip(),
        body.message_content.strip(),
    )
    if not all(values):
        raise HTTPException(status_code=422, detail="All simulation fields are required")

    # ── 1. Resolve company intelligence from email domain ──────────────
    resolver = CompanyResolver()
    company_info = resolver.resolve(body.sender_email.strip())

    resolved_domain = company_info["domain"]

    # Use resolver's company name (from email domain) as a more accurate source;
    # the user-provided company_name is kept for backward compatibility but the
    # domain-based name is preferred for research enrichment.
    effective_name = company_info["company_name"]

    company, contact, lead = _find_or_create_simulation_lead(
        db,
        effective_name,
        body.sender_name.strip(),
        body.sender_email.strip(),
        domain=resolved_domain,
    )

    # ── 2. Enrich company profile with resolver data ───────────────────
    if company_info.get("industry"):
        company.industry = company_info["industry"]
    if company_info.get("employees"):
        company.employee_count = company_info["employees"]
    profile = dict(company.profile_data or {})
    profile.update({
        "location": company_info.get("location") or profile.get("location", ""),
        "source": company_info.get("source", "manual_inbound"),
        "company_name": company.name,
    })
    company.profile_data = profile
    db.flush()

    # ── 3. Process inbound message ────────────────────────────────────
    logger.info(
        "[WORKFLOW] inbound started lead=%s company=%s",
        lead.id, company.name,
    )
    inbound = await process_inbound_message(
        InboundRequest(
            from_email=body.sender_email.strip(),
            from_name=body.sender_name.strip(),
            subject=f"Product discussion with {company.name}",
            body=body.message_content.strip(),
            lead_id=str(lead.id),
            contact_id=str(contact.id),
            company_id=str(company.id),
        ),
        db,
    )

    logger.info(
        "[WORKFLOW] inbound completed lead_id=%s task_id=%s",
        lead.id, inbound.get("task_id"),
    )
    logger.info("[LEAD] id=%s company=%s", lead.id, company.name)

    # ── 4. Run research enrichment directly (not via create_research_task) ─
    report = (
        db.query(models.ResearchReport)
        .filter(models.ResearchReport.company_id == company.id)
        .order_by(models.ResearchReport.created_at.desc())
        .first()
    )

    report_id: str | None = None
    if not report:
        logger.info(
            "[WORKFLOW] research started for company=%s domain=%s",
            effective_name, resolved_domain,
        )
        try:
            # Execute research agent directly (same pattern as inbound agent)
            research_task_id = uuid.uuid4()
            research_runtime = build_runtime(db)
            research_tm = TaskManager(db)

            research_input = AgentTaskInput(
                id=research_task_id,
                agent_type="research",
                input_data={
                    "company_name": effective_name,
                    "domain": resolved_domain,
                },
                company_id=company.id,
            )

            research_db_task = research_tm.create_task(research_input)
            research_tm.mark_running(research_db_task.id)

            research_context = AgentContext(
                task_id=research_task_id,
                correlation_id=f"research-{research_task_id}",
            )

            research_result = await research_runtime.execute(
                research_context, research_input,
            )

            # Persist ResearchReport
            findings = research_result.output_data.get("findings", {})
            research_report = models.ResearchReport(
                id=uuid.uuid4(),
                company_id=company.id,
                task_id=research_task_id,
                summary=research_result.summary,
                findings=findings,
                sources=[{"url": s} for s in findings.get("sources", [])],
                provider=research_result.output_data.get("providers_used"),
            )
            db.add(research_report)

            # Update company profile with research data
            if findings.get("industry"):
                company.industry = findings["industry"]
            if findings.get("employee_count"):
                company.employee_count = findings["employee_count"]
            company.profile_data = findings

            research_tm.mark_completed(research_task_id, research_result.output_data)
            db.commit()  # Persist research independently so it survives qualification failures

            # Save the new report_id for qualification
            report_id = str(research_report.id)

            signal_count = len(findings.get("recent_signals", []))
            # evidence is stored at top-level output_data, not in findings
            evidence_count = len(research_result.output_data.get("evidence", []))
            logger.info(
                "[WORKFLOW] research completed signals=%s evidence=%s company=%s",
                signal_count, evidence_count, effective_name,
            )

            # Re-fetch the report for downstream use
            report = research_report

        except Exception as exc:
            logger.warning(
                "[WORKFLOW] research failed for %s: %s — continuing without enrichment",
                effective_name, exc,
            )

    else:
        report_id = str(report.id) if report.id else None
        logger.info(
            "[WORKFLOW] existing research found report_id=%s",
            report_id,
        )

    # ── 5. Qualification with research context ────────────────────────
    logger.info("[WORKFLOW] qualification started for lead=%s", lead.id)
    qualification = None
    try:
        qualification = await create_qualification_task(
            QualifyRequest(
                company_name=company.name,
                lead_id=str(lead.id),
                report_id=report_id,
            ),
            db,
        )
        qual_score = qualification.get("score") if isinstance(qualification, dict) else None
        logger.info(
            "[WORKFLOW] qualification completed lead=%s score=%s",
            lead.id, qual_score,
        )
    except Exception as exc:
        logger.warning(
            "[WORKFLOW] qualification failed lead=%s error=%s — continuing",
            lead.id, exc,
        )

    # ── 6. Pipeline evaluation ────────────────────────────────────────
    logger.info("[WORKFLOW] pipeline started for lead=%s", lead.id)
    pipeline = None
    try:
        pipeline = await evaluate_pipeline(PipelineEvaluateRequest(lead_id=str(lead.id)), db)
        logger.info(
            "[WORKFLOW] pipeline completed lead=%s",
            lead.id,
        )
    except Exception as exc:
        logger.warning(
            "[WORKFLOW] pipeline failed lead=%s error=%s — continuing",
            lead.id, exc,
        )

    # ── 7. Return result (always include lead_id) ─────────────────────
    logger.info(
        "[WORKFLOW] completed lead=%s company=%s score=%s",
        lead.id, company.name,
        qualification.get("score") if isinstance(qualification, dict) else None,
    )

    return {
        "task_id": inbound.get("task_id", ""),
        "company": company.name,
        "contact": body.sender_name.strip(),
        "lead_id": str(lead.id),
        "qualification": qualification,
        "pipeline": pipeline,
        "company_domain": resolved_domain,
        "company_industry": company.industry or "",
    }


@router.get("/inbound/{task_id}/simulation")
async def get_inbound_simulation(task_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return a compact cross-agent result for the inbound simulation page."""
    try:
        task_uid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")
    message = db.query(models.InboundMessage).filter(
        models.InboundMessage.task_id == task_uid
    ).first()
    if not message or not message.lead_id:
        raise HTTPException(status_code=404, detail="Simulated inbound message not found")
    lead = db.query(models.Lead).filter(models.Lead.id == message.lead_id).first()
    company = db.query(models.Company).filter(models.Company.id == message.company_id).first()
    contact = db.query(models.Contact).filter(models.Contact.id == message.contact_id).first()
    qualification = db.query(models.QualificationResult).filter(
        models.QualificationResult.lead_id == message.lead_id
    ).order_by(models.QualificationResult.created_at.desc()).first()
    pipeline_task = db.query(models.AgentTask).filter(
        models.AgentTask.agent_type == "pipeline", models.AgentTask.lead_id == message.lead_id
    ).order_by(models.AgentTask.created_at.desc()).first()
    recommended_action = (
        (pipeline_task.output_data or {}).get("recommended_action", {})
        if pipeline_task
        else {}
    )
    contact_name = (
        " ".join(filter(None, [contact.first_name, contact.last_name]))
        if contact
        else message.from_name
    )
    return {
        "company": company.name if company else "Unknown",
        "contact": contact_name,
        "intent": message.intent or "other",
        "sentiment": message.sentiment,
        "urgency": message.urgency,
        "score": qualification.overall_score if qualification else None,
        "priority": qualification.priority if qualification else None,
        "recommendation": _simulation_recommendation_text(
            recommended_action if isinstance(recommended_action, dict) else {},
            message.follow_up_suggestion,
        ),
        "pipeline_stage": lead.status if lead else None,
        "lead_id": str(lead.id) if lead else None,
    }


@router.post("/inbound", response_model=InboundResponse, status_code=202)
async def process_inbound_message(
    body: InboundRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Process an inbound message — classify intent, sentiment, urgency, and generate reply."""
    if not body.body:
        raise HTTPException(status_code=422, detail="Message body is required")

    # ── 1. Resolve lead/contact context ────────────────────────────────
    lead_context: dict[str, Any] = {
        "lead_id": body.lead_id,
        "contact_id": body.contact_id,
        "company_id": body.company_id,
    }

    # ── 2. Create task and runtime ────────────────────────────────────
    task_id = uuid.uuid4()
    correlation_id = f"inbound-{task_id}"
    runtime = build_runtime(db)
    tm = TaskManager(db)

    task_input = AgentTaskInput(
        id=task_id,
        agent_type="inbound",
        input_data={
            "message": {
                "from_email": body.from_email,
                "from_name": body.from_name,
                "subject": body.subject,
                "body": body.body,
                "channel": body.channel,
            },
            "lead_context": lead_context,
        },
        company_id=uuid.UUID(body.company_id) if body.company_id else None,
        lead_id=uuid.UUID(body.lead_id) if body.lead_id else None,
    )

    # ── 3. Execute with lifecycle ─────────────────────────────────────
    db_task = tm.create_task(task_input)
    tm.mark_running(db_task.id)
    context = AgentContext(task_id=task_id, correlation_id=correlation_id)

    try:
        result = await runtime.execute(context, task_input)
        output = result.output_data
        analysis = output.get("analysis", {})
        action = output.get("lead_action", {})
        reply = output.get("suggested_reply", {})
        needs_approval = output.get("requires_human_approval", False)

        # ── 4. Persist InboundMessage ─────────────────────────────────
        msg = models.InboundMessage(
            id=uuid.uuid4(),
            task_id=task_id,
            from_email=body.from_email,
            from_name=body.from_name,
            channel=body.channel,
            subject=body.subject,
            body=body.body,
            lead_id=uuid.UUID(body.lead_id) if body.lead_id else None,
            contact_id=uuid.UUID(body.contact_id) if body.contact_id else None,
            company_id=uuid.UUID(body.company_id) if body.company_id else None,
            intent=analysis.get("intent"),
            sentiment=analysis.get("sentiment"),
            urgency=analysis.get("urgency"),
            confidence=analysis.get("confidence"),
            extracted_details=analysis.get("extracted_details"),
            lead_action=action.get("action"),
            suggested_status=action.get("suggested_status"),
            suggested_reply_subject=reply.get("subject"),
            suggested_reply_body=reply.get("body"),
            follow_up_suggestion=output.get("follow_up_suggestion"),
            status="pending_review" if needs_approval else "approved",
            provider=output.get("providers_used"),
        )
        db.add(msg)

        if needs_approval:
            tm.mark_waiting_for_approval(task_id)
        else:
            tm.mark_completed(task_id, output)
        db.commit()

        reply_preview = ""
        if reply and reply.get("body"):
            reply_preview = reply["body"][:200]

        return InboundResponse(
            task_id=str(task_id),
            message_id=str(msg.id),
            status=msg.status,
            intent=analysis.get("intent"),
            sentiment=analysis.get("sentiment"),
            urgency=analysis.get("urgency"),
            lead_action=action.get("action"),
            requires_human_approval=needs_approval,
            suggested_reply_preview=reply_preview,
        ).model_dump()

    except Exception as exc:
        db.rollback()
        try:
            tm.mark_failed(task_id, str(exc))
            db.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail=f"Inbound processing failed: {exc}"
        )


@router.get("/inbound/{task_id}", response_model=InboundAnalysisResponse)
async def get_inbound_analysis(
    task_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve the full inbound analysis including intent, sentiment, and reply."""
    try:
        uid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")

    task = db.query(models.AgentTask).filter(models.AgentTask.id == uid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    msg = db.query(models.InboundMessage).filter(
        models.InboundMessage.task_id == uid
    ).first()

    return InboundAnalysisResponse(
        task_id=str(task.id),
        status=task.status,
        agent_type=task.agent_type,
        message_id=str(msg.id) if msg else None,
        message={
            "from_email": msg.from_email if msg else "",
            "from_name": msg.from_name if msg else "",
            "subject": msg.subject if msg else "",
            "body": msg.body if msg else "",
            "channel": msg.channel if msg else "",
        } if msg else {},
        analysis={
            "intent": msg.intent if msg else None,
            "sentiment": msg.sentiment if msg else None,
            "urgency": msg.urgency if msg else None,
            "confidence": msg.confidence if msg else None,
            "extracted_details": msg.extracted_details if msg else {},
        } if msg else {},
        lead_action={
            "action": msg.lead_action if msg else None,
            "status_update": msg.suggested_status if msg else None,
        } if msg else {},
        suggested_reply={
            "subject": msg.suggested_reply_subject if msg else None,
            "body": msg.suggested_reply_body if msg else None,
        } if msg else {},
        approval_summary={
            "status": msg.status if msg else "",
            "reviewed_by": msg.reviewed_by if msg else None,
            "reviewed_at": msg.reviewed_at.isoformat()
            if msg and msg.reviewed_at
            else None,
        } if msg else {},
        created_at=task.created_at.isoformat() if task.created_at else None,
        completed_at=task.updated_at.isoformat()
        if task.status in ("completed", "waiting_for_approval") and task.updated_at
        else None,
        error_message=task.error_message,
    ).model_dump()


@router.post("/inbound/{message_id}/approve", response_model=InboundApproveResponse)
async def approve_inbound_reply(
    message_id: str,
    body: InboundApproveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Approve a suggested reply for an inbound message."""
    try:
        uid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid message_id format")

    msg = db.query(models.InboundMessage).filter(
        models.InboundMessage.id == uid
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Inbound message not found")

    msg.status = "approved"
    msg.reviewed_by = body.approved_by or "unknown"
    msg.review_notes = body.approval_notes
    msg.reviewed_at = datetime.now(timezone.utc)

    # Mark the agent task as completed
    task = db.query(models.AgentTask).filter(
        models.AgentTask.id == msg.task_id
    ).first()
    if task:
        task.status = "completed"

    # Apply suggested status update to lead if applicable
    if msg.suggested_status and msg.lead_id:
        lead = db.query(models.Lead).filter(
            models.Lead.id == msg.lead_id
        ).first()
        if lead:
            lead.status = msg.suggested_status

    db.commit()

    return InboundApproveResponse(
        message_id=str(msg.id),
        status="approved",
    ).model_dump()


@router.post("/inbound/{message_id}/reject", response_model=InboundRejectResponse)
async def reject_inbound_reply(
    message_id: str,
    body: InboundRejectRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reject a suggested reply for an inbound message."""
    try:
        uid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid message_id format")

    msg = db.query(models.InboundMessage).filter(
        models.InboundMessage.id == uid
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Inbound message not found")

    msg.status = "rejected"
    msg.review_notes = body.rejected_reason
    msg.reviewed_at = datetime.now(timezone.utc)

    # Mark the agent task as completed (rejected)
    task = db.query(models.AgentTask).filter(
        models.AgentTask.id == msg.task_id
    ).first()
    if task:
        task.status = "completed"

    db.commit()

    return InboundRejectResponse(
        message_id=str(msg.id),
        status="rejected",
    ).model_dump()


# ── Pipeline endpoints ─────────────────────────────────────────────────


class PipelineEvaluateRequest(BaseModel):
    lead_id: str = ""


class PipelineEvaluateResponse(BaseModel):
    task_id: str
    lead_id: str | None = None
    status: str
    current_stage: str | None = None
    stage_health: str | None = None
    stagnation_risk: str | None = None
    recommended_action: dict[str, Any] = {}


class PipelineEvaluationResponse(BaseModel):
    task_id: str
    status: str
    agent_type: str
    lead_id: str | None = None
    evaluation: dict[str, Any] = {}
    lead_health: dict[str, Any] = {}
    recommended_action: dict[str, Any] = {}
    created_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


class PipelineAdvanceRequest(BaseModel):
    new_stage: str = ""
    reason: str = ""
    advanced_by: str = ""


class PipelineAdvanceResponse(BaseModel):
    lead_id: str
    new_stage: str
    previous_stage: str
    status_id: str | None = None


class PipelineLeadItem(BaseModel):
    lead_id: str
    company_name: str = ""
    current_stage: str = "unknown"
    stage_health: str = "unknown"
    days_in_stage: int = 0
    overall_score: int | None = None
    priority: str | None = None
    next_action: str = ""


class PipelineLeadsResponse(BaseModel):
    leads: list[dict[str, Any]] = []
    total: int = 0


@router.post("/pipeline/evaluate", response_model=PipelineEvaluateResponse, status_code=202)
async def evaluate_pipeline(
    body: PipelineEvaluateRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Evaluate a lead's pipeline position and recommend next action."""
    if not body.lead_id:
        raise HTTPException(status_code=422, detail="lead_id is required")

    try:
        lead_uid = uuid.UUID(body.lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid lead_id format")

    # ── 1. Resolve lead and aggregated data ────────────────────────────
    lead = db.query(models.Lead).filter(models.Lead.id == lead_uid).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    current_stage = lead.status or "new"

    # Build aggregated data from all phases
    aggregated: dict[str, Any] = {
        "research_task": {},
        "qualification_results": [],
        "outreach_drafts": [],
        "inbound_messages": [],
        "conversations": [],
    }

    # Research
    tasks = db.query(models.AgentTask).filter(
        models.AgentTask.lead_id == lead_uid
    ).order_by(models.AgentTask.created_at.desc()).all()
    for t in tasks:
        if t.agent_type == "research":
            aggregated["research_task"] = {
                "status": t.status,
                "completed_at": t.updated_at.isoformat() if t.updated_at else None,
                "findings": t.output_data.get("findings", {}) if t.output_data else {},
            }
        elif t.agent_type == "qualification":
            qual = db.query(models.QualificationResult).filter(
                models.QualificationResult.task_id == t.id
            ).first()
            if qual:
                aggregated["qualification_results"].append({
                    "overall_score": qual.overall_score,
                    "priority": qual.priority,
                    "created_at": qual.created_at.isoformat() if qual.created_at else None,
                })
        elif t.agent_type == "outreach":
            draft = db.query(models.OutreachDraft).filter(
                models.OutreachDraft.task_id == t.id
            ).first()
            if draft:
                aggregated["outreach_drafts"].append({
                    "status": draft.status,
                    "urgency": draft.strategy_urgency,
                    "created_at": draft.created_at.isoformat() if draft.created_at else None,
                    "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
                })

    # Inbound messages
    messages = db.query(models.InboundMessage).filter(
        models.InboundMessage.lead_id == lead_uid
    ).order_by(models.InboundMessage.received_at.desc()).limit(5).all()
    for m in messages:
        aggregated["inbound_messages"].append({
            "intent": m.intent,
            "sentiment": m.sentiment,
            "urgency": m.urgency,
            "channel": m.channel,
            "received_at": m.received_at.isoformat() if m.received_at else None,
        })

    # Conversations
    conversations = db.query(models.Conversation).filter(
        models.Conversation.lead_id == lead_uid
    ).order_by(models.Conversation.occurred_at.desc()).limit(5).all()
    for c in conversations:
        aggregated["conversations"].append({
            "direction": c.direction,
            "channel": c.channel,
            "occurred_at": c.occurred_at.isoformat() if c.occurred_at else None,
        })

    # Compute days in stage from pipeline status or lead created_at
    pipeline_entry = db.query(models.PipelineStatus).filter(
        models.PipelineStatus.lead_id == lead_uid,
        models.PipelineStatus.is_current == True,  # noqa: E712
    ).first()
    if pipeline_entry and pipeline_entry.entered_at:
        days_in_stage = (datetime.now(timezone.utc) - pipeline_entry.entered_at).days
    else:
        days_in_stage = (
            datetime.now(timezone.utc) - lead.created_at
        ).days if lead.created_at else 0

    # ── 2. Create task and runtime ────────────────────────────────────
    task_id = uuid.uuid4()
    correlation_id = f"pipeline-{task_id}"
    runtime = build_runtime(db)
    tm = TaskManager(db)

    task_input = AgentTaskInput(
        id=task_id,
        agent_type="pipeline",
        input_data={
            "lead_id": body.lead_id,
            "current_stage": current_stage,
            "days_in_stage": days_in_stage,
            "aggregated_data": aggregated,
        },
        lead_id=lead_uid,
    )

    # ── 3. Execute with lifecycle ─────────────────────────────────────
    db_task = tm.create_task(task_input)
    tm.mark_running(db_task.id)
    context = AgentContext(task_id=task_id, correlation_id=correlation_id)

    try:
        result = await runtime.execute(context, task_input)
        output = result.output_data

        tm.mark_completed(task_id, output)
        db.commit()

        evaluation = output.get("evaluation", {})
        recommended = output.get("recommended_action", {})

        return PipelineEvaluateResponse(
            task_id=str(task_id),
            lead_id=body.lead_id,
            status="completed",
            current_stage=evaluation.get("current_stage"),
            stage_health=evaluation.get("stage_health"),
            stagnation_risk=evaluation.get("stagnation_risk"),
            recommended_action=recommended,
        ).model_dump()

    except Exception as exc:
        db.rollback()
        try:
            tm.mark_failed(task_id, str(exc))
            db.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail=f"Pipeline evaluation failed: {exc}"
        )


@router.get("/pipeline/leads", response_model=PipelineLeadsResponse)
async def list_pipeline_leads(
    stage: str | None = None,
    health: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List leads with their current pipeline status."""
    query = db.query(models.Lead)

    if stage:
        query = query.filter(models.Lead.status == stage)

    leads = query.order_by(models.Lead.updated_at.desc()).limit(limit).all()

    result: list[dict[str, Any]] = []
    for lead in leads:
        company_name = ""
        if lead.company_id:
            company = db.query(models.Company).filter(
                models.Company.id == lead.company_id
            ).first()
            if company:
                company_name = company.name

        # Get current pipeline status
        pipeline_status = db.query(models.PipelineStatus).filter(
            models.PipelineStatus.lead_id == lead.id,
            models.PipelineStatus.is_current == True,  # noqa: E712
        ).first()

        days_in_stage = 0
        if pipeline_status and pipeline_status.entered_at:
            days_in_stage = (
                datetime.now(timezone.utc) - pipeline_status.entered_at
            ).days
        else:
            days_in_stage = (
                datetime.now(timezone.utc) - lead.created_at
            ).days if lead.created_at else 0

        stage_health = _compute_stage_health(
            lead.status or "new", days_in_stage
        )

        # Skip if filtering by health
        if health and stage_health != health:
            continue

        result.append({
            "lead_id": str(lead.id),
            "company_name": company_name,
            "current_stage": lead.status or "new",
            "stage_health": stage_health,
            "days_in_stage": days_in_stage,
            "overall_score": lead.score,
            "priority": _score_to_priority(lead.score),
            "next_action": pipeline_status.recommended_next_action
            if pipeline_status else "",
        })

    return PipelineLeadsResponse(
        leads=result,
        total=len(result),
    ).model_dump()


@router.get("/pipeline/{task_id}", response_model=PipelineEvaluationResponse)
async def get_pipeline_evaluation(
    task_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve the full pipeline evaluation result."""
    try:
        uid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")

    task = db.query(models.AgentTask).filter(models.AgentTask.id == uid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    output = task.output_data or {}

    return PipelineEvaluationResponse(
        task_id=str(task.id),
        status=task.status,
        agent_type=task.agent_type,
        lead_id=str(task.lead_id) if task.lead_id else None,
        evaluation=output.get("evaluation", {}),
        lead_health=output.get("lead_health", {}),
        recommended_action=output.get("recommended_action", {}),
        created_at=task.created_at.isoformat() if task.created_at else None,
        completed_at=task.updated_at.isoformat()
        if task.status == "completed" and task.updated_at
        else None,
        error_message=task.error_message,
    ).model_dump()


@router.post("/pipeline/{lead_id}/advance", response_model=PipelineAdvanceResponse)
async def advance_pipeline(
    lead_id: str,
    body: PipelineAdvanceRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Manually advance a lead to the next pipeline stage (human override)."""
    try:
        lead_uid = uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid lead_id format")

    lead = db.query(models.Lead).filter(models.Lead.id == lead_uid).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not body.new_stage:
        raise HTTPException(status_code=422, detail="new_stage is required")

    previous_stage = lead.status or "new"

    # Mark current pipeline status as not current
    current_status = db.query(models.PipelineStatus).filter(
        models.PipelineStatus.lead_id == lead_uid,
        models.PipelineStatus.is_current == True,  # noqa: E712
    ).first()
    if current_status:
        current_status.is_current = False

    # Create new pipeline status record
    new_status = models.PipelineStatus(
        id=uuid.uuid4(),
        lead_id=lead_uid,
        stage=body.new_stage,
        is_current=True,
        entered_by="human",
        reason=body.reason,
    )
    db.add(new_status)

    # Update lead status
    lead.status = body.new_stage

    db.commit()

    return PipelineAdvanceResponse(
        lead_id=str(lead.id),
        new_stage=body.new_stage,
        previous_stage=previous_stage,
        status_id=str(new_status.id),
    ).model_dump()


# ── Task Logs endpoint ──────────────────────────────────────────────


class TaskLogsResponse(BaseModel):
    task_id: str
    logs: list[dict[str, Any]] = []


@router.get("/activity/tasks/{task_id}/logs", response_model=TaskLogsResponse)
async def get_task_logs(
    task_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve step-level execution logs for an agent task."""
    try:
        uid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task_id format")

    task = db.query(models.AgentTask).filter(models.AgentTask.id == uid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    logs = db.query(models.AgentLog).filter(
        models.AgentLog.task_id == uid
    ).order_by(models.AgentLog.created_at.asc()).all()

    return TaskLogsResponse(
        task_id=str(task.id),
        logs=[
            {
                "id": str(log.id),
                "level": log.level,
                "event_type": log.event_type,
                "message": log.message,
                "data": log.data,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    ).model_dump()


# ── Lead detail endpoint ──────────────────────────────────────────────


class LeadDetailResponse(BaseModel):
    lead_id: str
    company_name: str = ""
    domain: str = ""
    industry: str = ""
    employee_count: int | None = None
    location: str = ""
    description: str = ""
    business_signals: list[str] = []
    technology_signals: list[str] = []
    pain_points: list[str] = []
    flytbase_relevance: str = ""
    current_stage: str = "new"
    stage_health: str = "unknown"
    days_in_stage: int = 0
    overall_score: int | None = None
    priority: str | None = None


@router.get("/leads/{lead_id}/detail", response_model=LeadDetailResponse)
async def get_lead_detail(
    lead_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get full lead detail including company profile and pipeline status."""
    try:
        uid = uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid lead_id format")

    lead = db.query(models.Lead).filter(models.Lead.id == uid).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Company data
    company = db.query(models.Company).filter(
        models.Company.id == lead.company_id
    ).first() if lead.company_id else None

    # Pipeline status
    pipeline_status = db.query(models.PipelineStatus).filter(
        models.PipelineStatus.lead_id == uid,
        models.PipelineStatus.is_current == True,  # noqa: E712
    ).first()

    days_in_stage = 0
    if pipeline_status and pipeline_status.entered_at:
        days_in_stage = (
            datetime.now(timezone.utc) - pipeline_status.entered_at
        ).days
    elif lead.created_at:
        days_in_stage = (
            datetime.now(timezone.utc) - lead.created_at
        ).days

    current_stage = lead.status or "new"
    stage_health = _compute_stage_health(current_stage, days_in_stage)

    profile = company.profile_data or {} if company else {}

    # Location is stored in profile_data, not a top-level column
    location = profile.get("location", "") or ""

    return LeadDetailResponse(
        lead_id=str(lead.id),
        company_name=company.name if company else "",
        domain=company.domain if company else "",
        industry=company.industry or profile.get("industry", ""),
        employee_count=company.employee_count or profile.get("employee_count"),
        location=location,
        description=profile.get("description", ""),
        business_signals=profile.get("business_signals", []),
        technology_signals=profile.get("technology_signals", []),
        pain_points=profile.get("pain_points", []),
        flytbase_relevance=profile.get("flytbase_relevance", ""),
        current_stage=current_stage,
        stage_health=stage_health,
        days_in_stage=days_in_stage,
        overall_score=lead.score,
        priority=_score_to_priority(lead.score),
    ).model_dump()


# ── Pipeline helpers ────────────────────────────────────────────────────


def _score_to_priority(score: int | None) -> str | None:
    """Convert a numeric score to a priority label."""
    if score is None:
        return None
    if score >= 70:
        return "HOT"
    if score >= 40:
        return "WARM"
    return "COLD"


# ── Activity endpoint ──────────────────────────────────────────────────


class ActivityResponse(BaseModel):
    tasks: list[dict[str, Any]] = []
    total: int = 0


@router.get("/activity", response_model=ActivityResponse)
async def list_activity(
    limit: int = 20,
    agent_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent agent tasks for the activity feed."""
    query = db.query(models.AgentTask).order_by(models.AgentTask.updated_at.desc())

    if agent_type:
        query = query.filter(models.AgentTask.agent_type == agent_type)
    if status:
        query = query.filter(models.AgentTask.status == status)

    tasks = query.limit(limit).all()

    result: list[dict[str, Any]] = []
    for t in tasks:
        summary = t.output_data.get("summary", "") if t.output_data else ""
        company_name = ""
        if t.company_id:
            company = db.query(models.Company).filter(
                models.Company.id == t.company_id
            ).first()
            if company:
                company_name = company.name
        result.append({
            "task_id": str(t.id),
            "agent_type": t.agent_type,
            "status": t.status,
            "summary": summary or company_name or "",
            "company_name": company_name,
            "log_count": len(t.logs) if t.logs else 0,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.updated_at.isoformat() if t.updated_at else None,
            "requires_human_approval": t.requires_human_approval,
        })

    return ActivityResponse(
        tasks=result,
        total=len(result),
    ).model_dump()
