from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
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
        self._lock_dir = base_dir / ".locks"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.runbooks_dir.mkdir(parents=True, exist_ok=True)
        self.executions_dir.mkdir(parents=True, exist_ok=True)
        self._lock_dir.mkdir(parents=True, exist_ok=True)

    def _runbook_path(self, runbook_id: str) -> Path:
        return self.runbooks_dir / f"{runbook_id}.json"

    def _execution_path(self, execution_id: str) -> Path:
        return self.executions_dir / f"{execution_id}.json"

    def _lock_path(self, kind: str, record_id: str) -> Path:
        return self._lock_dir / f"{kind}-{record_id}.lock"

    def _acquire_lock(self, lock_path: Path):
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _release_lock(self, fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _atomic_write(self, target: Path, content: str, kind: str, record_id: str) -> None:
        lock_path = self._lock_path(kind, record_id)
        lock_fd = self._acquire_lock(lock_path)
        try:
            target_dir = target.parent
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(target_dir),
                prefix=target.name + ".",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                os.replace(tmp_path, str(target))
            except OSError:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        finally:
            self._release_lock(lock_fd)

    def save_runbook(self, runbook: Runbook) -> None:
        runbook.updated_at = datetime.now()
        content = runbook.model_dump_json(indent=2)
        path = self._runbook_path(runbook.id)
        self._atomic_write(path, content, "runbook", runbook.id)

    def load_runbook(self, runbook_id: str) -> Optional[Runbook]:
        path = self._runbook_path(runbook_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Runbook.model_validate(data)

    def delete_runbook(self, runbook_id: str) -> bool:
        lock_path = self._lock_path("runbook", runbook_id)
        lock_fd = self._acquire_lock(lock_path)
        try:
            path = self._runbook_path(runbook_id)
            if path.exists():
                path.unlink()
                return True
            return False
        finally:
            self._release_lock(lock_fd)

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
        content = execution.model_dump_json(indent=2)
        path = self._execution_path(execution.id)
        self._atomic_write(path, content, "execution", execution.id)

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
