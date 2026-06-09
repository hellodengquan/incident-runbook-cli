from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import ExecutionRecord, Runbook


class RunbookStorage:
    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            home = Path.home()
            base_dir = home / ".runbook-cli"
        self.base_dir = base_dir
        self.runbooks_dir = base_dir / "runbooks"
        self.executions_dir = base_dir / "executions"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.runbooks_dir.mkdir(parents=True, exist_ok=True)
        self.executions_dir.mkdir(parents=True, exist_ok=True)

    def _runbook_path(self, runbook_id: str) -> Path:
        return self.runbooks_dir / f"{runbook_id}.json"

    def _execution_path(self, execution_id: str) -> Path:
        return self.executions_dir / f"{execution_id}.json"

    def save_runbook(self, runbook: Runbook) -> None:
        runbook.updated_at = datetime.now()
        path = self._runbook_path(runbook.id)
        path.write_text(
            runbook.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_runbook(self, runbook_id: str) -> Optional[Runbook]:
        path = self._runbook_path(runbook_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Runbook.model_validate(data)

    def delete_runbook(self, runbook_id: str) -> bool:
        path = self._runbook_path(runbook_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_runbooks(self) -> List[Runbook]:
        runbooks = []
        for file in sorted(self.runbooks_dir.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                runbooks.append(Runbook.model_validate(data))
            except (json.JSONDecodeError, KeyError):
                continue
        runbooks.sort(key=lambda r: r.updated_at, reverse=True)
        return runbooks

    def find_runbook_by_name(self, name: str) -> Optional[Runbook]:
        for runbook in self.list_runbooks():
            if runbook.name == name:
                return runbook
        return None

    def save_execution(self, execution: ExecutionRecord) -> None:
        path = self._execution_path(execution.id)
        path.write_text(
            execution.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        path = self._execution_path(execution_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExecutionRecord.model_validate(data)

    def list_executions(self, runbook_id: Optional[str] = None) -> List[ExecutionRecord]:
        executions = []
        for file in sorted(self.executions_dir.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                exec_record = ExecutionRecord.model_validate(data)
                if runbook_id and exec_record.runbook_id != runbook_id:
                    continue
                executions.append(exec_record)
            except (json.JSONDecodeError, KeyError):
                continue
        executions.sort(key=lambda e: e.started_at or datetime.min, reverse=True)
        return executions

    def get_active_execution(self) -> Optional[ExecutionRecord]:
        for exec_record in self.list_executions():
            if exec_record.status in ("running", "paused"):
                return exec_record
        return None
