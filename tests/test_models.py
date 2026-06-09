from __future__ import annotations

import json
from datetime import datetime

import pytest

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


class TestStepModel:
    def test_default_id_generation(self):
        step = Step(title="测试步骤")
        assert step.id is not None
        assert len(step.id) == 8

    def test_custom_id(self):
        step = Step(id="custom-id", title="测试步骤")
        assert step.id == "custom-id"

    def test_default_values(self):
        step = Step(title="测试步骤")
        assert step.description == ""
        assert step.expected_duration_minutes is None
        assert step.checklist == []

    def test_full_init(self):
        step = Step(
            title="确认故障",
            description="确认服务是否真的宕机",
            expected_duration_minutes=5,
            checklist=["ping", "telnet 端口"],
        )
        assert step.title == "确认故障"
        assert step.description == "确认服务是否真的宕机"
        assert step.expected_duration_minutes == 5
        assert step.checklist == ["ping", "telnet 端口"]

    def test_model_dump_json_roundtrip(self):
        step = Step(
            title="确认故障",
            description="描述",
            expected_duration_minutes=3,
            checklist=["a", "b", "c"],
        )
        raw = step.model_dump_json()
        parsed = Step.model_validate_json(raw)
        assert parsed.id == step.id
        assert parsed.title == step.title
        assert parsed.checklist == step.checklist


class TestRunbookModel:
    def test_default_id_and_timestamps(self):
        rb = Runbook(name="测试预案")
        assert rb.id is not None
        assert isinstance(rb.created_at, datetime)
        assert isinstance(rb.updated_at, datetime)

    def test_default_enums(self):
        rb = Runbook(name="测试预案")
        assert rb.severity == SeverityLevel.MEDIUM
        assert rb.status == RunbookStatus.DRAFT
        assert rb.steps == []
        assert rb.tags == []
        assert rb.created_by == "system"

    def test_custom_values(self, sample_runbook):
        assert sample_runbook.name == "MySQL 切换"
        assert sample_runbook.severity == SeverityLevel.CRITICAL
        assert sample_runbook.status == RunbookStatus.ACTIVE
        assert len(sample_runbook.steps) == 3
        assert sample_runbook.tags == ["db", "MySQL", "ha"]
        assert sample_runbook.created_by == "sre"

    def test_model_dump_contains_all_fields(self, sample_runbook):
        data = sample_runbook.model_dump(mode="json")
        for key in ["id", "name", "description", "severity", "status", "steps", "tags", "created_at", "updated_at", "created_by"]:
            assert key in data
        assert len(data["steps"]) == 3
        assert data["severity"] == "critical"
        assert data["status"] == "active"

    def test_json_roundtrip(self, sample_runbook):
        raw = sample_runbook.model_dump_json(indent=2)
        reparsed = json.loads(raw)
        loaded = Runbook.model_validate(reparsed)
        assert loaded.id == sample_runbook.id
        assert loaded.name == sample_runbook.name
        assert loaded.severity == sample_runbook.severity
        assert [s.id for s in loaded.steps] == [s.id for s in sample_runbook.steps]
        assert loaded.tags == sample_runbook.tags

    def test_validate_extra_ignored_or_raises(self):
        data = {
            "id": "rb999",
            "name": "测试",
            "extra_field": "should be ignored",
        }
        rb = Runbook.model_validate(data)
        assert rb.name == "测试"


class TestExecutionStepModel:
    def test_defaults(self):
        es = ExecutionStep(step_id="st001", title="步骤1")
        assert es.status == StepStatus.PENDING
        assert es.started_at is None
        assert es.completed_at is None
        assert es.notes == ""
        assert es.operator is None

    def test_full(self):
        now = datetime.now()
        es = ExecutionStep(
            step_id="st001",
            title="步骤1",
            status=StepStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            notes="处理完毕",
            operator="张三",
        )
        assert es.status == StepStatus.COMPLETED
        assert es.operator == "张三"
        assert es.notes == "处理完毕"

    def test_json_roundtrip(self):
        now = datetime(2026, 6, 10, 9, 0, 0)
        es = ExecutionStep(
            step_id="st001",
            title="确认故障",
            status=StepStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            notes="OK",
            operator="张三",
        )
        raw = es.model_dump_json()
        parsed = ExecutionStep.model_validate_json(raw)
        assert parsed.status == StepStatus.COMPLETED
        assert parsed.started_at == now
        assert parsed.notes == "OK"


class TestExecutionRecordModel:
    def test_defaults(self):
        er = ExecutionRecord(
            runbook_id="rb001",
            runbook_name="测试预案",
            severity=SeverityLevel.MEDIUM,
        )
        assert er.id is not None
        assert er.status == ExecutionStatus.NOT_STARTED
        assert er.steps == []
        assert er.started_at is None
        assert er.completed_at is None
        assert er.operator == "oncall"
        assert er.incident_id is None
        assert er.summary == ""

    def test_full_init(self, completed_execution):
        assert completed_execution.status == ExecutionStatus.COMPLETED
        assert len(completed_execution.steps) == 3
        assert completed_execution.incident_id == "INC-20260610-001"
        assert completed_execution.summary == "切换成功恢复"
        for step in completed_execution.steps:
            assert step.status == StepStatus.COMPLETED
            assert step.started_at is not None
            assert step.completed_at is not None

    def test_json_roundtrip(self, sample_execution):
        raw = sample_execution.model_dump_json()
        parsed = ExecutionRecord.model_validate_json(raw)
        assert parsed.id == sample_execution.id
        assert parsed.runbook_name == sample_execution.runbook_name
        assert parsed.status == sample_execution.status
        assert len(parsed.steps) == len(sample_execution.steps)
        assert parsed.steps[0].notes == sample_execution.steps[0].notes


class TestEnumValues:
    @pytest.mark.parametrize("enum_cls,values", [
        (StepStatus, ["pending", "in_progress", "completed", "skipped", "failed"]),
        (RunbookStatus, ["draft", "active", "archived"]),
        (ExecutionStatus, ["not_started", "running", "paused", "completed", "failed"]),
        (SeverityLevel, ["low", "medium", "high", "critical"]),
    ])
    def test_enum_members(self, enum_cls, values):
        members = {e.value for e in enum_cls}
        assert members == set(values)

    def test_severity_comparable_order(self):
        order = [SeverityLevel.LOW, SeverityLevel.MEDIUM, SeverityLevel.HIGH, SeverityLevel.CRITICAL]
        values = [s.value for s in order]
        assert values == ["low", "medium", "high", "critical"]
