from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.contracts import AgentTaskInput
from app.db.models import AgentLog, AgentTask


class TaskManager:
    """Database-backed lifecycle manager for AgentTask records.

    Every agent uses this to:
    - Transition task states (pending → running → completed | failed)
    - Persist output data and error messages
    - Append structured audit log entries
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- lifecycle ----

    def create_task(self, task_input: AgentTaskInput) -> AgentTask:
        """Create a new AgentTask row with status ``pending``."""
        task = AgentTask(
            id=task_input.id,
            agent_type=task_input.agent_type,
            status="pending",
            company_id=task_input.company_id,
            lead_id=task_input.lead_id,
            input_data=task_input.input_data,
            requires_human_approval=task_input.requires_human_approval,
        )
        self._session.add(task)
        self._session.flush()
        return task

    def mark_running(self, task_id: UUID) -> AgentTask:
        task = self._get_task(task_id)
        task.status = "running"
        self._session.flush()
        return task

    def mark_completed(self, task_id: UUID, output_data: dict[str, Any]) -> AgentTask:
        task = self._get_task(task_id)
        task.status = "completed"
        task.output_data = output_data
        self._session.flush()
        return task

    def mark_failed(self, task_id: UUID, error: str) -> AgentTask:
        task = self._get_task(task_id)
        task.status = "failed"
        task.error_message = error
        self._session.flush()
        return task

    def mark_waiting_for_approval(self, task_id: UUID) -> AgentTask:
        task = self._get_task(task_id)
        task.status = "waiting_for_approval"
        self._session.flush()
        return task

    def get_task(self, task_id: UUID) -> AgentTask | None:
        return self._session.query(AgentTask).filter(AgentTask.id == task_id).first()

    # ---- logging ----

    def append_log(
        self,
        task_id: UUID,
        level: str,
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> AgentLog:
        log = AgentLog(
            id=uuid.uuid4(),
            task_id=task_id,
            level=level,
            event_type=event_type,
            message=message,
            data=data or {},
        )
        self._session.add(log)
        self._session.flush()
        return log

    def get_logs(self, task_id: UUID) -> list[AgentLog]:
        return (
            self._session.query(AgentLog)
            .filter(AgentLog.task_id == task_id)
            .order_by(AgentLog.created_at.asc())
            .all()
        )

    # ---- helpers ----

    def _get_task(self, task_id: UUID) -> AgentTask:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        return task
