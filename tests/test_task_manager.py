from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.contracts import AgentTaskInput
from app.core.task_manager import TaskManager
from app.db.models import AgentLog, AgentTask


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def tm(mock_session: MagicMock) -> TaskManager:
    return TaskManager(session=mock_session)


class TestTaskManagerLifecycle:
    def test_create_task(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_input = AgentTaskInput(
            id=uuid.uuid4(),
            agent_type="research",
            input_data={"company_name": "Acme"},
        )
        task = tm.create_task(task_input)
        assert task.id == task_input.id
        assert task.status == "pending"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_mark_running(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_id = uuid.uuid4()
        mock_task = AgentTask(id=task_id, status="pending")
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task

        result = tm.mark_running(task_id)
        assert result.status == "running"
        mock_session.flush.assert_called_once()

    def test_mark_completed(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_id = uuid.uuid4()
        mock_task = AgentTask(id=task_id, status="running")
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task

        output = {"report_id": "abc"}
        result = tm.mark_completed(task_id, output)
        assert result.status == "completed"
        assert result.output_data == output

    def test_mark_failed(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_id = uuid.uuid4()
        mock_task = AgentTask(id=task_id, status="running")
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task

        result = tm.mark_failed(task_id, "Something went wrong")
        assert result.status == "failed"
        assert result.error_message == "Something went wrong"

    def test_get_task_not_found(self, tm: TaskManager, mock_session: MagicMock) -> None:
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = tm.get_task(uuid.uuid4())
        assert result is None

    def test_get_task_found(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_id = uuid.uuid4()
        mock_task = AgentTask(id=task_id, status="pending")
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task

        result = tm.get_task(task_id)
        assert result is not None
        assert result.id == task_id


class TestTaskManagerLogging:
    def test_append_log(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_id = uuid.uuid4()
        log = tm.append_log(task_id, "info", "research.started", "Research began")
        assert log.task_id == task_id
        assert log.level == "info"
        assert log.event_type == "research.started"
        assert log.message == "Research began"
        mock_session.add.assert_called_once()

    def test_append_log_with_data(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_id = uuid.uuid4()
        log = tm.append_log(
            task_id, "debug", "tool.called", "Called web_search",
            data={"tool": "web_search", "query": "test"},
        )
        assert log.data == {"tool": "web_search", "query": "test"}

    def test_get_logs(self, tm: TaskManager, mock_session: MagicMock) -> None:
        task_id = uuid.uuid4()
        mock_logs = [
            AgentLog(
                id=uuid.uuid4(), task_id=task_id, level="info",
                event_type="test", message="log1",
            ),
        ]
        query_res = mock_session.query.return_value
        mock_query_chain = query_res.filter.return_value.order_by.return_value
        mock_query_chain.all.return_value = mock_logs

        logs = tm.get_logs(task_id)
        assert len(logs) == 1
        assert logs[0].message == "log1"
