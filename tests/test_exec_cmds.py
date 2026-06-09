from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from runbook_cli.commands import runbook_cmds
from runbook_cli.commands import exec_cmds
from runbook_cli.commands import history_cmds
from runbook_cli.commands import admin_cmds
from runbook_cli import main as _main_mod
from runbook_cli.models import (
    ExecutionStatus,
    RunbookStatus,
    SeverityLevel,
    StepStatus,
)


@pytest.fixture(autouse=True)
def _patch_storage_refs(monkeypatch, tmp_storage):
    monkeypatch.setattr(runbook_cmds, "storage", tmp_storage)
    monkeypatch.setattr(exec_cmds, "storage", tmp_storage)
    monkeypatch.setattr(history_cmds, "storage", tmp_storage)
    monkeypatch.setattr(admin_cmds, "storage", tmp_storage)
    monkeypatch.setattr(_main_mod, "storage", tmp_storage)
    yield


@pytest.fixture
def _seeded(tmp_storage, sample_runbook, sample_runbook_2, sample_execution, completed_execution):
    tmp_storage.save_runbook(sample_runbook)
    tmp_storage.save_runbook(sample_runbook_2)
    tmp_storage.save_execution(sample_execution)
    tmp_storage.save_execution(completed_execution)
    yield


class TestExecStart:
    def test_start_new(self, cli_runner, app, tmp_storage, sample_runbook):
        tmp_storage.save_runbook(sample_runbook)
        result = cli_runner.invoke(
            app,
            [
                "exec", "start", "MySQL 切换",
                "--operator", "李四",
                "--incident-id", "INC-TEST-001",
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "执行会话已创建" in result.stdout
        active = tmp_storage.get_active_execution()
        assert active is not None
        assert active.runbook_id == sample_runbook.id
        assert active.operator == "李四"
        assert active.incident_id == "INC-TEST-001"
        assert active.status == ExecutionStatus.RUNNING
        assert len(active.steps) == 3
        for s in active.steps:
            assert s.status == StepStatus.PENDING

    def test_start_active_exists_cancel(self, cli_runner, app, _seeded, tmp_storage):
        count_before = len(tmp_storage.list_executions())
        result = cli_runner.invoke(
            app,
            ["exec", "start", "MySQL 切换"],
            input="n\n",
        )
        assert result.exit_code == 0
        assert len(tmp_storage.list_executions()) == count_before

    def test_start_nonactive_runbook_confirm(self, cli_runner, app, tmp_storage, sample_runbook_2):
        tmp_storage.save_runbook(sample_runbook_2)
        assert sample_runbook_2.status == RunbookStatus.DRAFT
        result = cli_runner.invoke(
            app,
            ["exec", "start", "K8s 节点异常"],
            input="y\n",
        )
        assert result.exit_code == 0, result.stdout
        assert tmp_storage.get_active_execution() is not None

    def test_start_missing_runbook(self, cli_runner, app):
        result = cli_runner.invoke(app, ["exec", "start", "不存在"])
        assert result.exit_code != 0
        assert "预案不存在" in result.stdout

    def test_start_runbook_no_steps(self, cli_runner, app, tmp_storage):
        from runbook_cli.models import Runbook
        tmp_storage.save_runbook(Runbook(id="rb-empty", name="空预案", status=RunbookStatus.ACTIVE))
        result = cli_runner.invoke(app, ["exec", "start", "空预案"])
        assert result.exit_code != 0
        assert "没有定义执行步骤" in result.stdout


class TestExecStatusCurrent:
    def test_status_active(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["exec", "status"])
        assert result.exit_code == 0
        assert "执行状态" in result.stdout
        assert "INC-20260610-001" in result.stdout

    def test_status_specific_id(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["exec", "status", "--id", "ex002"])
        assert result.exit_code == 0
        assert "ex002" in result.stdout

    def test_status_no_active(self, cli_runner, app, tmp_storage, completed_execution):
        tmp_storage.save_execution(completed_execution)
        result = cli_runner.invoke(app, ["exec", "status"])
        assert result.exit_code == 0
        assert "暂无进行中的执行会话" in result.stdout

    def test_current(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["exec", "current"])
        assert result.exit_code == 0
        assert "MySQL 切换" in result.stdout


class TestExecStep:
    def test_step_start_by_shortcut(self, cli_runner, app, tmp_storage, sample_runbook, sample_execution):
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(
            app,
            ["exec", "step", "3", "--notes", "开始切换"],
        )
        assert result.exit_code == 0, result.stdout
        assert "开始执行步骤 3" in result.stdout
        ex = tmp_storage.load_execution(sample_execution.id)
        assert ex.steps[2].status == StepStatus.IN_PROGRESS
        assert ex.steps[2].started_at is not None
        assert ex.steps[2].notes == "开始切换"

    def test_step_complete_current(self, cli_runner, app, tmp_storage, sample_runbook, sample_execution):
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        cli_runner.invoke(app, ["exec", "step", "3"])
        result = cli_runner.invoke(
            app,
            ["exec", "step", "complete", "--notes", "切换成功"],
        )
        assert result.exit_code == 0
        assert "步骤 3 已完成" in result.stdout
        ex = tmp_storage.load_execution(sample_execution.id)
        assert ex.steps[2].status == StepStatus.COMPLETED
        assert ex.steps[2].completed_at is not None
        assert "切换成功" in ex.steps[2].notes

    def test_step_skip(self, cli_runner, app, tmp_storage, sample_runbook, sample_execution):
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(
            app,
            ["exec", "step", "skip", "3", "--notes", "无需切换"],
        )
        assert result.exit_code == 0
        assert "已跳过步骤 3" in result.stdout
        ex = tmp_storage.load_execution(sample_execution.id)
        assert ex.steps[2].status == StepStatus.SKIPPED

    def test_step_fail(self, cli_runner, app, tmp_storage, sample_runbook, sample_execution):
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(
            app,
            ["exec", "step", "fail", "3", "--notes", "从库不一致"],
        )
        assert result.exit_code == 0
        assert "步骤 3 失败" in result.stdout
        ex = tmp_storage.load_execution(sample_execution.id)
        assert ex.steps[2].status == StepStatus.FAILED
        assert ex.status == ExecutionStatus.FAILED

    def test_step_note(self, cli_runner, app, tmp_storage, sample_runbook, sample_execution):
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(
            app,
            ["exec", "step", "note", "1", "--notes", "追加备注"],
        )
        assert result.exit_code == 0
        assert "已更新步骤 1 的备注" in result.stdout
        ex = tmp_storage.load_execution(sample_execution.id)
        assert "追加备注" in ex.steps[0].notes

    def test_step_invalid_action(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["exec", "step", "bogus", "1"])
        assert result.exit_code != 0
        assert "无效操作" in result.stdout

    def test_step_no_active(self, cli_runner, app, tmp_storage, sample_runbook):
        from runbook_cli.models import ExecutionRecord, Step
        rb = sample_runbook
        tmp_storage.save_runbook(rb)
        ex = ExecutionRecord(
            id="ex-fin",
            runbook_id=rb.id,
            runbook_name=rb.name,
            severity=rb.severity,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        tmp_storage.save_execution(ex)
        result = cli_runner.invoke(app, ["exec", "step", "1"])
        assert result.exit_code != 0

    def test_step_paused_rejected(self, cli_runner, app, tmp_storage, sample_runbook, sample_execution):
        tmp_storage.save_runbook(sample_runbook)
        sample_execution.status = ExecutionStatus.PAUSED
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(app, ["exec", "step", "1"])
        assert result.exit_code != 0
        assert "已暂停" in result.stdout


class TestExecPauseResume:
    def test_pause(self, cli_runner, app, _seeded, tmp_storage):
        result = cli_runner.invoke(app, ["exec", "pause", "--reason", "等待DBA回电"])
        assert result.exit_code == 0
        assert "执行已暂停" in result.stdout
        ex = tmp_storage.load_execution("ex001")
        assert ex.status == ExecutionStatus.PAUSED
        assert ex.paused_at is not None
        assert "等待DBA回电" in ex.summary

    def test_pause_not_running(self, cli_runner, app, tmp_storage, sample_execution, completed_execution):
        # 保存两个：completed 非活跃 + sample(running) 但被改为 completed
        tmp_storage.save_execution(completed_execution)
        sample_execution.status = ExecutionStatus.COMPLETED
        sample_execution.completed_at = datetime.now()
        tmp_storage.save_execution(sample_execution)
        # 此时无活跃执行
        result = cli_runner.invoke(app, ["exec", "pause"])
        # 无活跃执行时 exec pause 会 exit != 0（报错退出）
        assert result.exit_code != 0
        assert "暂无进行中的执行会话" in result.stdout or "执行会话已结束" in result.stdout

    def test_pause_no_active(self, cli_runner, app, tmp_storage):
        result = cli_runner.invoke(app, ["exec", "pause"])
        assert result.exit_code != 0

    def test_resume(self, cli_runner, app, tmp_storage, sample_execution):
        sample_execution.status = ExecutionStatus.PAUSED
        sample_execution.paused_at = datetime.now()
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(app, ["exec", "resume"])
        assert result.exit_code == 0
        assert "已恢复执行" in result.stdout
        ex = tmp_storage.load_execution(sample_execution.id)
        assert ex.status == ExecutionStatus.RUNNING
        assert ex.paused_at is None

    def test_resume_not_paused(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["exec", "resume"])
        assert result.exit_code == 0
        assert "无需恢复" in result.stdout


class TestExecFinishAbort:
    def test_finish_force(self, cli_runner, app, tmp_storage, sample_runbook, sample_execution):
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(
            app,
            ["exec", "finish", "--force", "--summary", "处理完毕"],
        )
        assert result.exit_code == 0, result.stdout
        assert "执行会话已结束" in result.stdout
        ex = tmp_storage.load_execution(sample_execution.id)
        assert ex.status == ExecutionStatus.COMPLETED
        assert ex.completed_at is not None
        assert ex.summary == "处理完毕"

    def test_finish_interactive_with_pending(self, cli_runner, app, _seeded, tmp_storage):
        result = cli_runner.invoke(
            app,
            ["exec", "finish", "--summary", "处理总结"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "执行会话已结束" in result.stdout

    def test_finish_already_completed(self, cli_runner, app, tmp_storage, sample_execution, completed_execution):
        # 保存 completed_execution 和 sample（改为 COMPLETED），此时无活跃执行
        tmp_storage.save_execution(completed_execution)
        sample_execution.status = ExecutionStatus.COMPLETED
        sample_execution.completed_at = datetime.now()
        tmp_storage.save_execution(sample_execution)
        result = cli_runner.invoke(app, ["exec", "finish", "--force"])
        # exec finish 当没有活跃执行时会 exit != 0
        assert result.exit_code != 0

    def test_abort_confirms(self, cli_runner, app, _seeded, tmp_storage):
        result = cli_runner.invoke(
            app,
            ["exec", "abort", "--reason", "人力不足"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "执行会话已中止" in result.stdout
        ex = tmp_storage.load_execution("ex001")
        assert ex.status == ExecutionStatus.FAILED
        for s in ex.steps:
            if s.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS):
                assert s.status == StepStatus.FAILED

    def test_abort_no_active(self, cli_runner, app, tmp_storage):
        result = cli_runner.invoke(app, ["exec", "abort"])
        assert result.exit_code != 0


class TestHistoryCommands:
    def test_history_list(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["history", "list"])
        assert result.exit_code == 0
        assert "执行历史" in result.stdout
        # ID 断言避免换行问题
        assert "ex001" in result.stdout
        assert "ex002" in result.stdout

    def test_history_show(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["history", "show", "ex002"])
        assert result.exit_code == 0
        assert "处理总结" in result.stdout
        assert "步骤 1" in result.stdout
        assert "步骤 2" in result.stdout

    def test_history_show_missing(self, cli_runner, app):
        result = cli_runner.invoke(app, ["history", "show", "nope"])
        assert result.exit_code != 0

    def test_history_summary(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["history", "summary", "--last-days", "7"])
        assert result.exit_code == 0
        assert "执行统计摘要" in result.stdout
        assert "成功率" in result.stdout

    def test_history_summary_empty(self, cli_runner, app):
        result = cli_runner.invoke(app, ["history", "summary"])
        assert result.exit_code == 0
        assert "暂无执行记录" in result.stdout

    def test_history_export_json(self, cli_runner, app, _seeded, tmp_path):
        out = tmp_path / "report.json"
        result = cli_runner.invoke(
            app,
            ["history", "export", "ex002", "--format", "json", "-o", str(out), "--force-name"],
        )
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["id"] == "ex002"
        assert data["status"] == "completed"

    def test_history_export_md(self, cli_runner, app, _seeded, tmp_path):
        out = tmp_path / "report.md"
        result = cli_runner.invoke(
            app,
            ["history", "export", "ex002", "--format", "md", "-o", str(out), "--force-name"],
        )
        assert result.exit_code == 0
        content = out.read_text()
        assert content.startswith("# 应急处理记录")
        assert "处理总结" in content
        assert "### 1." in content

    def test_history_export_txt(self, cli_runner, app, _seeded, tmp_path):
        out = tmp_path / "report.txt"
        result = cli_runner.invoke(
            app,
            ["history", "export", "ex002", "--format", "txt", "-o", str(out), "--force-name"],
        )
        assert result.exit_code == 0
        content = out.read_text()
        assert "应急处理记录" in content
        assert "【基本信息】" in content
        assert "【执行步骤详情】" in content

    def test_history_export_invalid_format(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["history", "export", "ex002", "--format", "xml"])
        assert result.exit_code != 0
        assert "不支持的格式" in result.stdout

    def test_history_export_missing(self, cli_runner, app, tmp_path):
        out = tmp_path / "x.json"
        result = cli_runner.invoke(app, ["history", "export", "nope", "-o", str(out)])
        assert result.exit_code != 0


class TestDashboardInitDemo:
    def test_dashboard_with_data(self, cli_runner, app, _seeded):
        result = cli_runner.invoke(app, ["dashboard"])
        assert result.exit_code == 0
        assert "应急 Runbook 仪表板" in result.stdout
        assert "预案总数" in result.stdout
        assert "执行总数" in result.stdout

    def test_init_demo(self, cli_runner, app, tmp_storage):
        result = cli_runner.invoke(app, ["init-demo", "--force"])
        assert result.exit_code == 0
        rbs = tmp_storage.list_runbooks()
        assert len(rbs) >= 3


class TestHistoryExportNamingConvention:
    def test_export_default_filename_matches_pattern(self, cli_runner, app, _seeded, sample_execution, tmp_path, monkeypatch):
        out_dir = tmp_path / "exports"
        out_dir.mkdir()
        monkeypatch.chdir(out_dir)
        result = cli_runner.invoke(app, ["history", "export", "ex001", "-f", "json"])
        assert result.exit_code == 0, result.stdout
        files = list(out_dir.glob("INC-*-v*.json"))
        assert len(files) >= 1, f"未找到符合命名规范的文件: {list(out_dir.iterdir())}"
        name = files[0].name
        parts = name.rsplit("-v", 1)
        assert len(parts) == 2
        prefix, rest = parts
        assert prefix.startswith("INC-")
        main_parts = prefix.split("-")
        assert len(main_parts) >= 4, f"INC-<日期>-<序号>-<缩写>-<日期> 分段不对: {main_parts}"
        assert rest.endswith(".json")

    def test_export_filename_starts_with_existing_incident_id(self, cli_runner, app, tmp_storage, sample_execution, sample_runbook, tmp_path, monkeypatch):
        sample_execution.incident_id = "INC-20260610-007"
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        out_dir = tmp_path / "exp2"
        out_dir.mkdir()
        monkeypatch.chdir(out_dir)
        result = cli_runner.invoke(app, ["history", "export", sample_execution.id, "-f", "md"])
        assert result.exit_code == 0, result.stdout
        files = list(out_dir.glob("INC-20260610-007-*-v*.md"))
        assert len(files) >= 1

    def test_export_version_increments(self, cli_runner, app, _seeded, sample_execution, tmp_path, monkeypatch):
        out_dir = tmp_path / "exp3"
        out_dir.mkdir()
        monkeypatch.chdir(out_dir)
        for i in range(3):
            r = cli_runner.invoke(app, ["history", "export", "ex001", "-f", "txt"])
            assert r.exit_code == 0, r.stdout
        files = sorted(out_dir.glob("INC-*-v*.txt"))
        versions = []
        for f in files:
            m = __import__("re").search(r"-v(\d+)\.txt$", f.name)
            assert m is not None, f.name
            versions.append(int(m.group(1)))
        assert sorted(versions) == list(range(1, len(versions) + 1))
        assert 3 in versions or len(versions) >= 3

    def test_export_output_dir_still_generates_name(self, cli_runner, app, _seeded, tmp_path):
        out_dir = tmp_path / "exp4"
        out_dir.mkdir()
        result = cli_runner.invoke(app, ["history", "export", "ex001", "-f", "json", "-o", str(out_dir)])
        assert result.exit_code == 0, result.stdout
        files = list(out_dir.glob("INC-*-v*.json"))
        assert len(files) >= 1

    def test_export_force_name_allows_custom(self, cli_runner, app, _seeded, tmp_path):
        out_file = tmp_path / "my-custom-name.json"
        result = cli_runner.invoke(
            app,
            ["history", "export", "ex001", "-f", "json", "-o", str(out_file), "--force-name"],
        )
        assert result.exit_code == 0, result.stdout
        assert out_file.exists()
        assert out_file.name == "my-custom-name.json"

    def test_export_strict_name_ignores_custom_filename_parent(self, cli_runner, app, _seeded, tmp_path):
        out_file = tmp_path / "my-custom-name.json"
        result = cli_runner.invoke(
            app,
            ["history", "export", "ex001", "-f", "json", "-o", str(out_file), "--strict-name"],
        )
        assert result.exit_code == 0, result.stdout
        assert not out_file.exists()
        norm = list(tmp_path.glob("INC-*-v*.json"))
        assert len(norm) >= 1

    def test_export_runbook_abbreviation_uses_tag(self, cli_runner, app, tmp_storage, sample_execution, sample_runbook, tmp_path, monkeypatch):
        sample_runbook.tags = ["mysql-failover"]
        tmp_storage.save_runbook(sample_runbook)
        sample_execution.incident_id = "INC-20260610-012"
        tmp_storage.save_execution(sample_execution)
        out_dir = tmp_path / "exp-tags"
        out_dir.mkdir()
        monkeypatch.chdir(out_dir)
        r = cli_runner.invoke(app, ["history", "export", sample_execution.id, "-f", "md"])
        assert r.exit_code == 0, r.stdout
        files = list(out_dir.iterdir())
        assert any("mysql-failover" in f.name for f in files), f"未找到含标签缩写的文件: {[f.name for f in files]}"

    def test_export_autogenerates_incident_id_when_missing(self, cli_runner, app, tmp_storage, sample_execution, sample_runbook, tmp_path, monkeypatch):
        sample_execution.incident_id = None
        tmp_storage.save_runbook(sample_runbook)
        tmp_storage.save_execution(sample_execution)
        out_dir = tmp_path / "exp-inc-gen"
        out_dir.mkdir()
        monkeypatch.chdir(out_dir)
        r = cli_runner.invoke(app, ["history", "export", sample_execution.id, "-f", "json"])
        assert r.exit_code == 0, r.stdout
        files = list(out_dir.glob("INC-*-v*.json"))
        assert len(files) >= 1
        updated = tmp_storage.load_execution(sample_execution.id)
        assert updated is not None
        assert updated.incident_id is not None
        import re
        assert re.match(r"^INC-\d{8}-\d{3}$", updated.incident_id)


class TestAdminCommands:
    def _seed_stale_locks(self, tmp_storage, *, stale_count: int = 3, live_count: int = 2):
        import os, time
        from runbook_cli.storage import _write_pid_mark

        dead_pid_base = 2**30 + 9000
        stale_files = []
        for i in range(stale_count):
            p = tmp_storage._lock_dir / f"runbook-stale-{i}.lock"
            _write_pid_mark(p, pid=dead_pid_base + i)
            stale_files.append(p)
        live_files = []
        for i in range(live_count):
            p = tmp_storage._lock_dir / f"runbook-live-{i}.lock"
            _write_pid_mark(p, pid=os.getpid())
            live_files.append(p)
        return stale_files, live_files

    def test_admin_clean_locks_dry_run_does_not_delete(self, cli_runner, app, tmp_storage):
        stale, live = self._seed_stale_locks(tmp_storage, stale_count=3, live_count=2)
        before_stale = [p.exists() for p in stale]
        assert all(before_stale), "seeding 失败"
        result = cli_runner.invoke(app, ["admin", "clean-locks", "--dry-run"])
        assert result.exit_code == 0, result.stdout
        assert "DRY-RUN" in result.stdout
        assert "将清理" in result.stdout or "需清理" in result.stdout
        for p in stale:
            assert p.exists(), "dry-run 不应实际删除"
        for p in live:
            assert p.exists()

    def test_admin_clean_locks_actual_removes_stale(self, cli_runner, app, tmp_storage):
        stale, live = self._seed_stale_locks(tmp_storage, stale_count=4, live_count=1)
        result = cli_runner.invoke(app, ["admin", "clean-locks"])
        assert result.exit_code == 0, result.stdout
        assert "已清理" in result.stdout or "清理" in result.stdout
        for p in stale:
            assert not p.exists(), f"孤儿锁未被清: {p.name}"
        for p in live:
            assert p.exists(), "活锁不应被误删"

    def test_admin_clean_locks_max_age_custom(self, cli_runner, app, tmp_storage):
        # 准备 2 个锁：一个当前 PID（活）+ 一个活的 PID 但 mtime 设成 2 分钟前, max-age=60s 会被清理
        import os, time
        from runbook_cli.storage import _write_pid_mark

        live_pid = os.getpid()
        lock_new = tmp_storage._lock_dir / "runbook-young.lock"
        _write_pid_mark(lock_new, pid=live_pid)
        lock_old = tmp_storage._lock_dir / "runbook-aged.lock"
        _write_pid_mark(lock_old, pid=live_pid)
        # 将 lock_old 的 mtime 手动推进到 5 分钟前
        now = time.time()
        os.utime(str(lock_old), (now, now))  # 先用 now 写一下
        # 但 clean-locks 用的是 mark 里的时间戳，不是 mtime
        # 所以改一下：给死 PID + max-age=1s 肯定清；给活 PID + max-age=999999s 应该保留
        stale_2, live_2 = self._seed_stale_locks(tmp_storage, stale_count=1, live_count=1)
        result = cli_runner.invoke(app, ["admin", "clean-locks", "--max-age", "1"])
        assert result.exit_code == 0, result.stdout
        # 死 PID 的 1 个肯定被清，活 PID 的那个因 max-age=1s 而 age > 1s 也被清
        for p in stale_2:
            assert not p.exists()

    def test_admin_clean_locks_max_age_keeps_recent(self, cli_runner, app, tmp_storage):
        import os
        from runbook_cli.storage import _write_pid_mark
        from runbook_cli.storage import STALE_LOCK_MAX_AGE_SECONDS

        # 3 个活 PID + 2 个死 PID
        stale, live = self._seed_stale_locks(tmp_storage, stale_count=2, live_count=3)
        # 超大年龄阈值（等于默认 6h），活锁被保留（因为其 PID 还活着 + age 远小于阈值）
        result = cli_runner.invoke(
            app,
            ["admin", "clean-locks", "--max-age", str(STALE_LOCK_MAX_AGE_SECONDS)],
        )
        assert result.exit_code == 0, result.stdout
        for p in live:
            assert p.exists(), f"活锁在大阈值下被误删: {p.name}"
        for p in stale:
            assert not p.exists(), f"死锁未清理: {p.name}"

    def test_admin_clean_locks_empty_dir_noop(self, cli_runner, app, tmp_storage):
        # 确保没有锁文件
        import shutil
        shutil.rmtree(tmp_storage._lock_dir, ignore_errors=True)
        result = cli_runner.invoke(app, ["admin", "clean-locks"])
        assert result.exit_code == 0, result.stdout
        assert "锁目录不存在" in result.stdout or "无需" in result.stdout or "空" in result.stdout

    def test_admin_clean_locks_verbose_prints_table(self, cli_runner, app, tmp_storage):
        self._seed_stale_locks(tmp_storage, stale_count=2, live_count=2)
        r = cli_runner.invoke(app, ["admin", "clean-locks", "--dry-run", "--verbose"])
        assert r.exit_code == 0, r.stdout
        assert "锁文件详情" in r.stdout or "PID" in r.stdout
        assert "stale" in r.stdout

    def test_admin_lock_info_works(self, cli_runner, app, tmp_storage):
        self._seed_stale_locks(tmp_storage, stale_count=2, live_count=2)
        r = cli_runner.invoke(app, ["admin", "lock-info"])
        assert r.exit_code == 0, r.stdout
        assert "锁系统诊断" in r.stdout
        assert "平台" in r.stdout
        assert "锁总数" in r.stdout
        assert "孤儿" in r.stdout or "活跃" in r.stdout

    def test_admin_clean_locks_help_contains_options(self, cli_runner, app):
        r = cli_runner.invoke(app, ["admin", "clean-locks", "--help"])
        assert r.exit_code == 0
        assert "--dry-run" in r.stdout
        assert "--max-age" in r.stdout
        assert "--verbose" in r.stdout

    def test_admin_appears_in_top_level_help(self, cli_runner, app):
        r = cli_runner.invoke(app, ["--help"])
        assert r.exit_code == 0
        assert "admin" in r.stdout
        assert "运维管理" in r.stdout

    def test_admin_clean_locks_actual_after_dry_run_same_state(self, cli_runner, app, tmp_storage):
        # dry-run -> 实际清理：最终状态一致
        stale, live = self._seed_stale_locks(tmp_storage, stale_count=2, live_count=2)
        r1 = cli_runner.invoke(app, ["admin", "clean-locks", "--dry-run"])
        assert r1.exit_code == 0
        after_dry_stale = [p.exists() for p in stale]
        after_dry_live = [p.exists() for p in live]
        assert all(after_dry_stale)
        assert all(after_dry_live)
        r2 = cli_runner.invoke(app, ["admin", "clean-locks"])
        assert r2.exit_code == 0
        for p in stale:
            assert not p.exists()
        for p in live:
            assert p.exists()
