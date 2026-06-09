from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from runbook_cli.models import (
    ExecutionStatus,
    RunbookStatus,
    SeverityLevel,
    StepStatus,
)


class TestRunbookStorageBasics:
    def test_storage_dirs_created(self, tmp_path):
        from runbook_cli.storage import RunbookStorage

        storage = RunbookStorage(base_dir=tmp_path)
        assert (tmp_path / "runbooks").exists()
        assert (tmp_path / "executions").exists()
        assert storage.base_dir == tmp_path

    def test_default_storage_dir_is_home(self):
        from runbook_cli.storage import RunbookStorage

        storage = RunbookStorage()
        assert str(storage.base_dir).endswith(".runbook-cli")

    def test_save_and_load_runbook(self, tmp_storage, sample_runbook):
        tmp_storage.save_runbook(sample_runbook)
        loaded = tmp_storage.load_runbook(sample_runbook.id)
        assert loaded is not None
        assert loaded.id == sample_runbook.id
        assert loaded.name == sample_runbook.name
        assert loaded.severity == SeverityLevel.CRITICAL
        assert len(loaded.steps) == 3
        assert loaded.steps[0].checklist == ["检查告警", "telnet 3306", "mysql 连接"]

    def test_save_updates_updated_at(self, tmp_storage, sample_runbook):
        original = sample_runbook.updated_at
        tmp_storage.save_runbook(sample_runbook)
        loaded = tmp_storage.load_runbook(sample_runbook.id)
        assert loaded.updated_at >= original

    def test_load_nonexistent_runbook_returns_none(self, tmp_storage):
        assert tmp_storage.load_runbook("nonexistent") is None

    def test_runbook_json_file_created(self, tmp_storage, sample_runbook):
        tmp_storage.save_runbook(sample_runbook)
        path = tmp_storage.runbooks_dir / f"{sample_runbook.id}.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["id"] == sample_runbook.id
        assert data["name"] == sample_runbook.name

    def test_corrupted_json_skipped_in_list(self, tmp_storage, sample_runbook):
        tmp_storage.save_runbook(sample_runbook)
        bad = tmp_storage.runbooks_dir / "bad.json"
        bad.write_text("{not valid json:::")
        result = tmp_storage.list_runbooks()
        assert len(result) == 1
        assert result[0].id == sample_runbook.id


class TestRunbookListAndFind:
    def test_list_empty(self, tmp_storage):
        assert tmp_storage.list_runbooks() == []

    def test_list_multiple_sorted_by_updated_desc(self, storage_with_data, sample_runbook, sample_runbook_2, sample_runbook_3):
        result = storage_with_data.list_runbooks()
        ids = [r.id for r in result]
        # save_runbook 顺序: rb001 -> rb002 -> rb003，updated_at 依次增大，排序应倒序
        assert ids == [sample_runbook_3.id, sample_runbook_2.id, sample_runbook.id]

    def test_list_count(self, storage_with_data):
        assert len(storage_with_data.list_runbooks()) == 3

    def test_find_by_name_exact_match(self, storage_with_data, sample_runbook):
        found = storage_with_data.find_runbook_by_name(sample_runbook.name)
        assert found is not None
        assert found.id == sample_runbook.id

    def test_find_by_name_not_found(self, storage_with_data):
        assert storage_with_data.find_runbook_by_name("不存在的预案") is None


class TestRunbookDelete:
    def test_delete_existing(self, tmp_storage, sample_runbook):
        tmp_storage.save_runbook(sample_runbook)
        assert tmp_storage.delete_runbook(sample_runbook.id) is True
        assert tmp_storage.load_runbook(sample_runbook.id) is None
        assert len(tmp_storage.list_runbooks()) == 0

    def test_delete_nonexistent(self, tmp_storage):
        assert tmp_storage.delete_runbook("nonexistent") is False


class TestExecutionStorage:
    def test_save_and_load_execution(self, tmp_storage, sample_execution):
        tmp_storage.save_execution(sample_execution)
        loaded = tmp_storage.load_execution(sample_execution.id)
        assert loaded is not None
        assert loaded.id == sample_execution.id
        assert loaded.runbook_id == sample_execution.runbook_id
        assert loaded.status == ExecutionStatus.RUNNING
        assert len(loaded.steps) == 3
        assert loaded.steps[0].status == StepStatus.COMPLETED
        assert loaded.steps[0].notes == "主库宕机"
        assert loaded.incident_id == "INC-20260610-001"

    def test_load_nonexistent_execution(self, tmp_storage):
        assert tmp_storage.load_execution("nonexistent") is None

    def test_list_executions_all(self, storage_with_data):
        result = storage_with_data.list_executions()
        assert len(result) == 2

    def test_list_executions_filtered_by_runbook(self, storage_with_data, sample_runbook, sample_runbook_2):
        result = storage_with_data.list_executions(runbook_id=sample_runbook.id)
        assert len(result) == 2
        for e in result:
            assert e.runbook_id == sample_runbook.id
        assert storage_with_data.list_executions(runbook_id=sample_runbook_2.id) == []

    def test_get_active_execution(self, storage_with_data, sample_execution):
        active = storage_with_data.get_active_execution()
        assert active is not None
        assert active.id == sample_execution.id
        assert active.status in (ExecutionStatus.RUNNING, ExecutionStatus.PAUSED)

    def test_get_active_execution_none_when_all_done(self, tmp_storage, completed_execution):
        tmp_storage.save_execution(completed_execution)
        assert tmp_storage.get_active_execution() is None

    def test_execution_sorted_by_started_desc(self, storage_with_data, sample_execution, completed_execution):
        result = storage_with_data.list_executions()
        times = [e.started_at for e in result]
        assert times == sorted(times, reverse=True)

    def test_execution_without_started_sorts_last(self, tmp_storage, sample_execution, sample_runbook):
        from runbook_cli.models import ExecutionRecord, ExecutionStep

        no_start = ExecutionRecord(
            id="ex999",
            runbook_id=sample_runbook.id,
            runbook_name=sample_runbook.name,
            severity=sample_runbook.severity,
            steps=[],
            started_at=None,
        )
        tmp_storage.save_execution(sample_execution)
        tmp_storage.save_execution(no_start)
        ids = [e.id for e in tmp_storage.list_executions()]
        assert ids.index(sample_execution.id) < ids.index("ex999")


class TestStorageRoundTrip:
    def test_runbook_full_roundtrip(self, tmp_storage, sample_runbook):
        tmp_storage.save_runbook(sample_runbook)
        loaded = tmp_storage.load_runbook(sample_runbook.id)
        path = tmp_storage._runbook_path(sample_runbook.id)
        raw = path.read_text()
        reparsed = json.loads(raw)
        assert reparsed["id"] == loaded.id
        assert reparsed["steps"][0]["expected_duration_minutes"] == loaded.steps[0].expected_duration_minutes
        assert reparsed["tags"] == loaded.tags

    def test_execution_full_roundtrip(self, tmp_storage, completed_execution):
        tmp_storage.save_execution(completed_execution)
        loaded = tmp_storage.load_execution(completed_execution.id)
        assert loaded.status == ExecutionStatus.COMPLETED
        assert loaded.summary == "切换成功恢复"
        for step in loaded.steps:
            assert step.completed_at is not None
            assert step.started_at <= step.completed_at

    def test_delete_runbook_does_not_affect_executions(self, storage_with_data, sample_runbook):
        assert len(storage_with_data.list_executions()) == 2
        storage_with_data.delete_runbook(sample_runbook.id)
        assert len(storage_with_data.list_executions()) == 2


class TestConcurrentWriteSafety:
    def test_save_runbook_creates_lock_file(self, tmp_storage, sample_runbook):
        tmp_storage.save_runbook(sample_runbook)
        assert (tmp_storage._lock_dir / f"runbook-{sample_runbook.id}.lock").exists()

    def test_save_execution_creates_lock_file(self, tmp_storage, sample_execution):
        tmp_storage.save_execution(sample_execution)
        assert (tmp_storage._lock_dir / f"execution-{sample_execution.id}.lock").exists()

    def test_lock_dir_created(self, tmp_path):
        from runbook_cli.storage import RunbookStorage
        storage = RunbookStorage(base_dir=tmp_path)
        assert (tmp_path / ".locks").exists()

    def test_threaded_concurrent_runbook_saves_no_corruption(self, tmp_storage, sample_runbook):
        import threading
        import copy
        from runbook_cli.models import Runbook

        ids = [f"rb-thr-{i}" for i in range(20)]
        errors = []
        results: dict[str, Runbook | None] = {}
        lock = threading.Lock()

        def worker(i: int):
            try:
                rb = copy.deepcopy(sample_runbook)
                rb.id = ids[i]
                rb.name = f"Worker {i} Runbook"
                rb.description = "x" * (1024 * 3)
                tmp_storage.save_runbook(rb)
                with lock:
                    results[rb.id] = tmp_storage.load_runbook(rb.id)
            except Exception as e:
                with lock:
                    errors.append((i, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(ids))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert errors == [], f"线程写入报错: {errors[:5]}"
        for rid in ids:
            loaded = results.get(rid)
            assert loaded is not None, f"未读到 {rid}"
            raw = (tmp_storage._runbook_path(rid)).read_text(encoding="utf-8")
            parsed = json.loads(raw)
            reparsed = Runbook.model_validate(parsed)
            assert reparsed.id == rid

    def test_threaded_concurrent_same_runbook_atomic_updates(self, tmp_storage, sample_runbook):
        import threading
        import copy

        tmp_storage.save_runbook(sample_runbook)
        errors = []
        iterations = 30

        def worker(i: int):
            try:
                for j in range(5):
                    rb = tmp_storage.load_runbook(sample_runbook.id)
                    if rb is None:
                        continue
                    rb.name = f"Update-{i}-{j}"
                    rb.description = "y" * (1024 * 2)
                    tmp_storage.save_runbook(rb)
            except Exception as e:
                errors.append((i, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(iterations)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"并发更新报错: {errors[:5]}"
        loaded = tmp_storage.load_runbook(sample_runbook.id)
        assert loaded is not None
        raw = (tmp_storage._runbook_path(sample_runbook.id)).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert parsed["id"] == sample_runbook.id

    def test_process_fork_concurrent_execution_saves(self, tmp_storage, sample_execution):
        import os
        import multiprocessing as mp

        def worker(base_dir_str, wid: int):
            from runbook_cli.storage import RunbookStorage
            from runbook_cli.models import ExecutionRecord
            import copy
            s = RunbookStorage(base_dir=Path(base_dir_str))
            ex = copy.deepcopy(sample_execution)
            ex.id = f"ex-fork-{wid}"
            ex.summary = f"worker {wid} " + "z" * 4096
            s.save_execution(ex)

        # 使用 fork context
        ctx = mp.get_context("fork")
        procs = []
        for i in range(8):
            p = ctx.Process(target=worker, args=(str(tmp_storage.base_dir), i))
            procs.append(p)
            p.start()
        for p in procs:
            p.join(timeout=30)
            assert p.exitcode == 0, f"子进程 {p.pid} 退出码 {p.exitcode}"

        for i in range(8):
            ex_id = f"ex-fork-{i}"
            loaded = tmp_storage.load_execution(ex_id)
            assert loaded is not None, f"子进程 {i} 写入的执行记录丢失"
            raw = (tmp_storage._execution_path(ex_id)).read_text(encoding="utf-8")
            parsed = json.loads(raw)
            assert parsed["id"] == ex_id

    def test_multiprocess_same_execution_updates_stay_valid(self, tmp_storage, sample_execution):
        import multiprocessing as mp

        tmp_storage.save_execution(sample_execution)
        base = str(tmp_storage.base_dir)
        ex_id = sample_execution.id

        def worker(base_dir_str, wid: int):
            from runbook_cli.storage import RunbookStorage
            s = RunbookStorage(base_dir=Path(base_dir_str))
            for _ in range(6):
                ex = s.load_execution(ex_id)
                if ex is None:
                    continue
                ex.summary = f"worker {wid} update"
                s.save_execution(ex)

        ctx = mp.get_context("fork")
        procs = [ctx.Process(target=worker, args=(base, i)) for i in range(6)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=30)
            assert p.exitcode == 0

        raw = (tmp_storage._execution_path(ex_id)).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert parsed["id"] == ex_id
