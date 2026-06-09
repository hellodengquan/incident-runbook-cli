from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class RunbookStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class SeverityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Step(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str
    description: str = ""
    expected_duration_minutes: Optional[int] = None
    checklist: List[str] = Field(default_factory=list)


class Runbook(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    description: str = ""
    severity: SeverityLevel = SeverityLevel.MEDIUM
    status: RunbookStatus = RunbookStatus.DRAFT
    steps: List[Step] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "system"
    tags: List[str] = Field(default_factory=list)


class ExecutionStep(BaseModel):
    step_id: str
    title: str
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: str = ""
    operator: Optional[str] = None


class ExecutionRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    runbook_id: str
    runbook_name: str
    severity: SeverityLevel
    status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    steps: List[ExecutionStep] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    operator: str = "oncall"
    incident_id: Optional[str] = None
    summary: str = ""
