from __future__ import annotations

from pathlib import Path

import pytest

from runbook_cli import commands as _cmds_pkg
from runbook_cli.commands import runbook_cmds
from runbook_cli.commands import exec_cmds
from runbook_cli.commands import history_cmds
from runbook_cli import main as _main_mod
from runbook_cli.models import RunbookStatus, SeverityLevel


@pytest.fixture(autouse=True)
def _patch_storage_refs(monkeypatch, tmp_storage):
    """将所有模块内的 storage 变量替换为 tmp_storage 实例。"""
    monkeypatch.setattr(runbook_cmds, "storage", tmp_storage)
    monkeypatch.setattr(exec_cmds, "storage", tmp_storage)
    monkeypatch.setattr(history_cmds, "storage", tmp_storage)
    monkeypatch.setattr(_main_mod, "storage", tmp_storage)
    yield


@pytest.fixture
def _seed(storage_with_data, _patch_storage_refs):
    yield


class TestRunbookCreate:
    def test_create_no_interactive_basic(self, cli_runner, app, tmp_storage):
        result = cli_runner.invoke(
            app,
            [
                "runbook", "create",
                "--name", "测试预案",
                "--description", "描述A",
                "--severity", "high",
                "--tag", "TagA",
                "--tag", "TagB",
                "--created-by", "test-user",
                "--no-interactive",
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert "预案创建成功" in result.stdout
        assert "测试预案" in result.stdout
        all_rb = tmp_storage.list_runbooks()
        assert len(all_rb) == 1
        rb = all_rb[0]
        assert rb.name == "测试预案"
        assert rb.description == "描述A"
        assert rb.severity == SeverityLevel.HIGH
        assert rb.tags == ["TagA", "TagB"]
        assert rb.created_by == "test-user"

    def test_create_name_required_exit(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "create", "--no-interactive"])
        assert result.exit_code != 0

    def test_create_duplicate_confirmation_cancels(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.list_runbooks())
        result = cli_runner.invoke(
            app,
            [
                "runbook", "create",
                "--name", "MySQL 切换",
                "--no-interactive",
            ],
            input="n\n",
        )
        assert result.exit_code == 0
        assert len(tmp_storage.list_runbooks()) == count_before


class TestRunbookList:
    def test_list_empty(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "list"])
        assert result.exit_code == 0
        assert "暂无预案" in result.stdout

    def test_list_all(self, cli_runner, app, _seed):
        result = cli_runner.invoke(app, ["runbook", "list"])
        assert result.exit_code == 0
        assert "预案清单" in result.stdout
        # 使用 ID 断言，避免 Rich 表格换行截断中文
        assert "rb001" in result.stdout
        assert "rb002" in result.stdout
        assert "rb003" in result.stdout

    def test_list_filter_status(self, cli_runner, app, _seed):
        result = cli_runner.invoke(app, ["runbook", "list", "--status", "active"])
        assert result.exit_code == 0
        assert "rb001" in result.stdout
        assert "rb002" not in result.stdout

    def test_list_filter_severity(self, cli_runner, app, _seed):
        result = cli_runner.invoke(app, ["runbook", "list", "--severity", "critical"])
        assert result.exit_code == 0
        assert "rb001" in result.stdout
        assert "rb003" not in result.stdout

    def test_list_filter_tag(self, cli_runner, app, _seed):
        result = cli_runner.invoke(app, ["runbook", "list", "--tag", "k8s"])
        assert result.exit_code == 0
        assert "rb002" in result.stdout
        assert "rb001" not in result.stdout


class TestRunbookShow:
    def test_show_by_id(self, cli_runner, app, _seed):
        result = cli_runner.invoke(app, ["runbook", "show", "rb001"])
        assert result.exit_code == 0
        assert "rb001" in result.stdout
        assert "确认故障" in result.stdout
        assert "执行步骤" in result.stdout

    def test_show_by_name(self, cli_runner, app, _seed):
        result = cli_runner.invoke(app, ["runbook", "show", "MySQL 切换"])
        assert result.exit_code == 0
        assert "rb001" in result.stdout

    def test_show_missing(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "show", "不存在"])
        assert result.exit_code != 0
        assert "预案不存在" in result.stdout


class TestRunbookDelete:
    def test_delete_force(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.list_runbooks())
        result = cli_runner.invoke(app, ["runbook", "delete", "rb003", "--force"])
        assert result.exit_code == 0
        assert len(tmp_storage.list_runbooks()) == count_before - 1
        assert tmp_storage.load_runbook("rb003") is None

    def test_delete_interactive_confirm(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.list_runbooks())
        result = cli_runner.invoke(
            app,
            ["runbook", "delete", "服务 OOM"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert len(tmp_storage.list_runbooks()) == count_before - 1

    def test_delete_interactive_cancel(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.list_runbooks())
        result = cli_runner.invoke(
            app,
            ["runbook", "delete", "rb001"],
            input="n\n",
        )
        assert result.exit_code == 0
        assert len(tmp_storage.list_runbooks()) == count_before

    def test_delete_missing(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "delete", "xyz", "--force"])
        assert result.exit_code != 0


class TestRunbookEdit:
    def test_edit_name_and_severity(self, cli_runner, app, _seed, tmp_storage):
        result = cli_runner.invoke(
            app,
            [
                "runbook", "edit", "rb002",
                "--name", "K8s 节点故障(新)",
                "--severity", "critical",
                "--status", "active",
            ],
        )
        assert result.exit_code == 0
        assert "预案信息已更新" in result.stdout
        rb = tmp_storage.load_runbook("rb002")
        assert rb.name == "K8s 节点故障(新)"
        assert rb.severity == SeverityLevel.CRITICAL
        assert rb.status == RunbookStatus.ACTIVE

    def test_edit_tags(self, cli_runner, app, _seed, tmp_storage):
        result = cli_runner.invoke(
            app,
            [
                "runbook", "edit", "rb001",
                "--add-tag", "TagX",
                "--add-tag", "TagY",
                "--remove-tag", "MySQL",
            ],
        )
        assert result.exit_code == 0
        rb = tmp_storage.load_runbook("rb001")
        assert "TagX" in rb.tags
        assert "TagY" in rb.tags
        assert "MySQL" not in rb.tags

    def test_edit_no_changes(self, cli_runner, app, _seed):
        result = cli_runner.invoke(app, ["runbook", "edit", "rb001"])
        assert result.exit_code == 0
        assert "未指定任何修改项" in result.stdout

    def test_edit_missing(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "edit", "nope", "--name", "X"])
        assert result.exit_code != 0


class TestRunbookAddRemoveStep:
    def test_add_step_append(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.load_runbook("rb003").steps)
        result = cli_runner.invoke(
            app,
            [
                "runbook", "add-step", "rb003",
                "--title", "新步骤A",
                "--description", "描述A",
                "--duration", "7",
            ],
        )
        assert result.exit_code == 0
        rb = tmp_storage.load_runbook("rb003")
        assert len(rb.steps) == count_before + 1
        assert rb.steps[-1].title == "新步骤A"

    def test_add_step_insert_position(self, cli_runner, app, _seed, tmp_storage):
        result = cli_runner.invoke(
            app,
            [
                "runbook", "add-step", "rb001",
                "--title", "插入步骤",
                "--position", "2",
            ],
        )
        assert result.exit_code == 0
        rb = tmp_storage.load_runbook("rb001")
        assert rb.steps[1].title == "插入步骤"
        assert len(rb.steps) == 4

    def test_remove_step_force(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.load_runbook("rb001").steps)
        result = cli_runner.invoke(
            app,
            ["runbook", "remove-step", "rb001", "1", "--force"],
        )
        assert result.exit_code == 0
        rb = tmp_storage.load_runbook("rb001")
        assert len(rb.steps) == count_before - 1

    def test_remove_step_by_id_interactive(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.load_runbook("rb001").steps)
        result = cli_runner.invoke(
            app,
            ["runbook", "remove-step", "rb001", "st003"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert len(tmp_storage.load_runbook("rb001").steps) == count_before - 1

    def test_remove_step_invalid(self, cli_runner, app, _seed):
        result = cli_runner.invoke(
            app,
            ["runbook", "remove-step", "rb001", "999", "--force"],
        )
        assert result.exit_code != 0
        assert "步骤不存在" in result.stdout

    def test_remove_step_empty_runbook(self, cli_runner, app, tmp_storage):
        from runbook_cli.models import Runbook
        tmp_storage.save_runbook(Runbook(id="rb-empty", name="空预案"))
        result = cli_runner.invoke(
            app,
            ["runbook", "remove-step", "rb-empty", "1", "--force"],
        )
        assert result.exit_code == 0
        assert "暂无步骤" in result.stdout

    def test_add_step_missing_runbook(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "add-step", "missing", "--title", "X"])
        assert result.exit_code != 0


class TestRunbookActivateArchive:
    def test_activate_no_steps_confirm(self, cli_runner, app, tmp_storage):
        from runbook_cli.models import Runbook
        tmp_storage.save_runbook(Runbook(id="rb-new", name="无步骤预案"))
        result = cli_runner.invoke(
            app,
            ["runbook", "activate", "rb-new"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert tmp_storage.load_runbook("rb-new").status == RunbookStatus.ACTIVE

    def test_activate_with_steps(self, cli_runner, app, _seed, tmp_storage):
        result = cli_runner.invoke(app, ["runbook", "activate", "rb002"])
        assert result.exit_code == 0
        assert tmp_storage.load_runbook("rb002").status == RunbookStatus.ACTIVE

    def test_activate_missing(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "activate", "missing"])
        assert result.exit_code != 0

    def test_archive(self, cli_runner, app, _seed, tmp_storage):
        result = cli_runner.invoke(app, ["runbook", "archive", "rb001"])
        assert result.exit_code == 0
        assert tmp_storage.load_runbook("rb001").status == RunbookStatus.ARCHIVED


class TestRunbookCopy:
    def test_copy(self, cli_runner, app, _seed, tmp_storage):
        count_before = len(tmp_storage.list_runbooks())
        result = cli_runner.invoke(
            app,
            ["runbook", "copy", "rb001", "--name", "MySQL 切换-副本"],
        )
        assert result.exit_code == 0
        assert len(tmp_storage.list_runbooks()) == count_before + 1
        new_rb = tmp_storage.find_runbook_by_name("MySQL 切换-副本")
        assert new_rb is not None
        assert new_rb.id != "rb001"
        assert new_rb.status == RunbookStatus.DRAFT
        assert len(new_rb.steps) == 3

    def test_copy_missing(self, cli_runner, app):
        result = cli_runner.invoke(app, ["runbook", "copy", "missing", "--name", "X"])
        assert result.exit_code != 0
