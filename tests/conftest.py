from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "src"),
)

from runbook_cli.models import (
    ExecutionRecord,
    ExecutionStatus,
    ExecutionStep,
    Runbook,
    RunbookStatus,
    SeverityLevel,
    Step,
    StepStatus,
)
from runbook_cli.storage import RunbookStorage


@pytest.fixture
def tmp_storage(tmp_path) -> RunbookStorage:
    return RunbookStorage(base_dir=tmp_path)


@pytest.fixture
def sample_runbook() -> Runbook:
    return Runbook(
        id="rb001",
        name="MySQL 切换",
        description="MySQL 主库不可用时的主从切换",
        severity=SeverityLevel.CRITICAL,
        status=RunbookStatus.ACTIVE,
        steps=[
            Step(
                id="st001",
                title="确认故障",
                description="通过监控和连接测试",
                expected_duration_minutes=5,
                checklist=["检查告警", "telnet 3306", "mysql 连接"],
            ),
            Step(
                id="st002",
                title="通知干系人",
                description="通知 DBA",
                expected_duration_minutes=3,
                checklist=["电话 DBA", "群公告"],
            ),
            Step(
                id="st003",
                title="主从切换",
                description="提升从库",
                expected_duration_minutes=10,
            ),
        ],
        created_at=datetime(2026, 6, 1, 10, 0, 0),
        updated_at=datetime(2026, 6, 1, 10, 0, 0),
        created_by="sre",
        tags=["db", "MySQL", "ha"],
    )


@pytest.fixture
def sample_runbook_2() -> Runbook:
    return Runbook(
        id="rb002",
        name="K8s 节点异常",
        description="K8s 节点 NotReady",
        severity=SeverityLevel.HIGH,
        status=RunbookStatus.DRAFT,
        steps=[
            Step(id="st101", title="确认节点"),
            Step(id="st102", title="疏散 Pod"),
        ],
        created_at=datetime(2026, 6, 2, 10, 0, 0),
        updated_at=datetime(2026, 6, 2, 10, 0, 0),
        created_by="sre",
        tags=["k8s", "容器"],
    )


@pytest.fixture
def sample_runbook_3() -> Runbook:
    return Runbook(
        id="rb003",
        name="服务 OOM",
        description="Java 服务 OOM",
        severity=SeverityLevel.MEDIUM,
        status=RunbookStatus.ARCHIVED,
        steps=[Step(id="st201", title="堆转储")],
        created_at=datetime(2026, 5, 20, 10, 0, 0),
        updated_at=datetime(2026, 5, 25, 10, 0, 0),
        created_by="dev",
        tags=["app", "性能"],
    )


@pytest.fixture
def sample_execution(sample_runbook) -> ExecutionRecord:
    steps = [
        ExecutionStep(
            step_id="st001",
            title="确认故障",
            status=StepStatus.COMPLETED,
            started_at=datetime(2026, 6, 10, 9, 0, 0),
            completed_at=datetime(2026, 6, 10, 9, 0, 4),
            notes="主库宕机",
            operator="张三",
        ),
        ExecutionStep(
            step_id="st002",
            title="通知干系人",
            status=StepStatus.COMPLETED,
            started_at=datetime(2026, 6, 10, 9, 0, 5),
            completed_at=datetime(2026, 6, 10, 9, 0, 8),
            notes="已通知",
            operator="张三",
        ),
        ExecutionStep(
            step_id="st003",
            title="主从切换",
            status=StepStatus.PENDING,
        ),
    ]
    return ExecutionRecord(
        id="ex001",
        runbook_id=sample_runbook.id,
        runbook_name=sample_runbook.name,
        severity=sample_runbook.severity,
        status=ExecutionStatus.RUNNING,
        steps=steps,
        started_at=datetime(2026, 6, 10, 8, 59, 50),
        operator="张三",
        incident_id="INC-20260610-001",
    )


@pytest.fixture
def completed_execution(sample_runbook) -> ExecutionRecord:
    steps = [
        ExecutionStep(
            step_id="st001",
            title="确认故障",
            status=StepStatus.COMPLETED,
            started_at=datetime(2026, 6, 10, 9, 0, 0),
            completed_at=datetime(2026, 6, 10, 9, 0, 4),
            operator="张三",
        ),
        ExecutionStep(
            step_id="st002",
            title="通知干系人",
            status=StepStatus.COMPLETED,
            started_at=datetime(2026, 6, 10, 9, 0, 5),
            completed_at=datetime(2026, 6, 10, 9, 0, 8),
            operator="张三",
        ),
        ExecutionStep(
            step_id="st003",
            title="主从切换",
            status=StepStatus.COMPLETED,
            started_at=datetime(2026, 6, 10, 9, 0, 10),
            completed_at=datetime(2026, 6, 10, 9, 0, 20),
            notes="切换成功",
            operator="张三",
        ),
    ]
    return ExecutionRecord(
        id="ex002",
        runbook_id=sample_runbook.id,
        runbook_name=sample_runbook.name,
        severity=sample_runbook.severity,
        status=ExecutionStatus.COMPLETED,
        steps=steps,
        started_at=datetime(2026, 6, 10, 8, 59, 50),
        completed_at=datetime(2026, 6, 10, 9, 0, 25),
        operator="张三",
        incident_id="INC-20260610-001",
        summary="切换成功恢复",
    )


@pytest.fixture
def storage_with_data(
    tmp_storage,
    sample_runbook,
    sample_runbook_2,
    sample_runbook_3,
    sample_execution,
    completed_execution,
) -> RunbookStorage:
    tmp_storage.save_runbook(sample_runbook)
    tmp_storage.save_runbook(sample_runbook_2)
    tmp_storage.save_runbook(sample_runbook_3)
    tmp_storage.save_execution(sample_execution)
    tmp_storage.save_execution(completed_execution)
    return tmp_storage


@pytest.fixture
def cli_runner():
    from typer.testing import CliRunner

    return CliRunner()


@pytest.fixture
def app():
    from runbook_cli.main import app

    return app
