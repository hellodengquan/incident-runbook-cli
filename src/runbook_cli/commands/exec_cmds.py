from __future__ import annotations

from datetime import datetime
from typing import Optional

import typer

from ..models import (
    ExecutionRecord,
    ExecutionStatus,
    ExecutionStep,
    RunbookStatus,
    StepStatus,
)
from ..storage import RunbookStorage
from .. import ui

app = typer.Typer(help="执行步骤状态追踪", no_args_is_help=True)
storage = RunbookStorage()


@app.command("start")
def start_execution(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
    operator: str = typer.Option("oncall", "--operator", "-o", help="值班人员"),
    incident_id: Optional[str] = typer.Option(None, "--incident-id", "-i", help="关联事件ID"),
):
    """开始执行预案（创建新的执行会话）"""
    active = storage.get_active_execution()
    if active:
        ui.warning(f"存在进行中的执行会话: {active.id}")
        ui.info(f"预案: {active.runbook_name}, 状态: {active.status.value}")
        if not ui.confirm("是否仍要创建新的执行会话？", default=False):
            raise typer.Exit(0)

    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    if runbook.status != RunbookStatus.ACTIVE:
        ui.warning(f"预案状态为 '{runbook.status.value}'，建议先激活预案")
        if not ui.confirm("仍然开始执行？", default=False):
            raise typer.Exit(0)

    if not runbook.steps:
        ui.error("预案没有定义执行步骤，无法执行")
        raise typer.Exit(1)

    exec_steps = [
        ExecutionStep(step_id=s.id, title=s.title) for s in runbook.steps
    ]

    execution = ExecutionRecord(
        runbook_id=runbook.id,
        runbook_name=runbook.name,
        severity=runbook.severity,
        status=ExecutionStatus.RUNNING,
        steps=exec_steps,
        started_at=datetime.now(),
        operator=operator,
        incident_id=incident_id,
    )

    storage.save_execution(execution)
    ui.success(f"执行会话已创建: {execution.id}")
    ui.info("使用 'exec step' 命令逐个处理步骤")
    ui.print_execution_status(execution)


@app.command("status")
def execution_status(
    execution_id: Optional[str] = typer.Option(None, "--id", help="执行ID（默认查看当前进行中的）"),
):
    """查看当前执行状态"""
    if execution_id:
        execution = storage.load_execution(execution_id)
    else:
        execution = storage.get_active_execution()

    if execution is None:
        ui.warning("暂无进行中的执行会话")
        return

    ui.print_execution_status(execution)


@app.command("step")
def process_step(
    action: str = typer.Argument(
        ...,
        help="操作: start/complete/skip/fail/note 或步骤编号（从1开始，默认开始该步骤）",
    ),
    step_ref: Optional[str] = typer.Argument(None, help="步骤编号或步骤ID"),
    notes: str = typer.Option("", "--notes", "-n", help="操作备注"),
    execution_id: Optional[str] = typer.Option(None, "--exec-id", help="执行ID（默认当前进行中的）"),
):
    """处理执行步骤

    快捷用法（按顺序推进）：
      runbook exec step 1      -> 开始步骤1
      runbook exec step start 1 -> 同上
      runbook exec step complete -> 完成当前进行中的步骤
      runbook exec step complete 2 -> 标记步骤2为完成
    """
    execution = storage.load_execution(execution_id) if execution_id else storage.get_active_execution()
    if execution is None:
        ui.error("暂无进行中的执行会话，请先使用 'exec start' 开始执行")
        raise typer.Exit(1)

    if execution.status == ExecutionStatus.PAUSED:
        ui.warning("执行会话已暂停，请先使用 'exec resume' 恢复")
        raise typer.Exit(1)

    if execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
        ui.error(f"执行会话已结束（状态: {execution.status.value}）")
        raise typer.Exit(1)

    valid_actions = {"start", "complete", "skip", "fail", "note"}

    if action.isdigit() and step_ref is None:
        step_ref = action
        action = "start"
    elif action not in valid_actions:
        ui.error(f"无效操作: {action}，可用操作: {', '.join(valid_actions)} 或步骤编号")
        raise typer.Exit(1)

    def find_step_idx(ref: Optional[str]) -> Optional[int]:
        if ref is None:
            for i, s in enumerate(execution.steps):
                if s.status == StepStatus.IN_PROGRESS:
                    return i
            return None
        if ref.isdigit():
            idx = int(ref) - 1
            if 0 <= idx < len(execution.steps):
                return idx
        else:
            for i, s in enumerate(execution.steps):
                if s.step_id == ref:
                    return i
        return None

    step_idx = find_step_idx(step_ref)
    if step_idx is None:
        if step_ref is None:
            ui.error("没有进行中的步骤，请指定步骤编号或先使用 start 开始一个步骤")
        else:
            ui.error(f"步骤不存在: {step_ref}")
        raise typer.Exit(1)

    step = execution.steps[step_idx]
    now = datetime.now()

    if action == "start":
        if step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
            ui.warning(f"步骤 {step_idx + 1} 已标记为 {step.status.value}")
            if not ui.confirm("重新开始该步骤？", default=False):
                return
        for i, s in enumerate(execution.steps):
            if i != step_idx and s.status == StepStatus.IN_PROGRESS:
                s.status = StepStatus.PENDING
                ui.info(f"已将步骤 {i + 1} 恢复为待执行状态")
        step.status = StepStatus.IN_PROGRESS
        step.started_at = now
        step.operator = execution.operator
        if notes:
            step.notes = notes
        ui.success(f"开始执行步骤 {step_idx + 1}: {step.title}")

    elif action == "complete":
        if step.status == StepStatus.PENDING:
            step.started_at = now
            step.operator = execution.operator
        step.status = StepStatus.COMPLETED
        step.completed_at = now
        if notes:
            step.notes = (step.notes + "\n" + notes).strip() if step.notes else notes
        ui.success(f"步骤 {step_idx + 1} 已完成: {step.title}")

    elif action == "skip":
        step.status = StepStatus.SKIPPED
        step.completed_at = now
        if notes:
            step.notes = (step.notes + "\n" + notes).strip() if step.notes else notes
        ui.warning(f"已跳过步骤 {step_idx + 1}: {step.title}")

    elif action == "fail":
        step.status = StepStatus.FAILED
        step.completed_at = now
        execution.status = ExecutionStatus.FAILED
        execution.completed_at = now
        if notes:
            step.notes = (step.notes + "\n" + notes).strip() if step.notes else notes
        ui.error(f"步骤 {step_idx + 1} 失败，执行会话已终止: {step.title}")

    elif action == "note":
        if notes:
            step.notes = (step.notes + "\n" + notes).strip() if step.notes else notes
            ui.success(f"已更新步骤 {step_idx + 1} 的备注")
        else:
            ui.warning("未提供备注内容")
            return

    all_done = all(
        s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED)
        for s in execution.steps
    )
    if all_done and execution.status != ExecutionStatus.FAILED:
        has_failed = any(s.status == StepStatus.FAILED for s in execution.steps)
        if has_failed:
            execution.status = ExecutionStatus.FAILED
        else:
            execution.status = ExecutionStatus.COMPLETED
        execution.completed_at = now
        ui.success("所有步骤已处理完毕，执行会话结束")

    storage.save_execution(execution)
    ui.print_execution_status(execution)


@app.command("pause")
def pause_execution(
    reason: str = typer.Option("", "--reason", "-r", help="暂停原因"),
    execution_id: Optional[str] = typer.Option(None, "--id", help="执行ID（默认当前进行中的）"),
):
    """暂停执行"""
    execution = storage.load_execution(execution_id) if execution_id else storage.get_active_execution()
    if execution is None:
        ui.error("暂无进行中的执行会话")
        raise typer.Exit(1)

    if execution.status != ExecutionStatus.RUNNING:
        ui.warning(f"当前状态为 '{execution.status.value}'，无法暂停")
        return

    execution.status = ExecutionStatus.PAUSED
    execution.paused_at = datetime.now()
    if reason:
        execution.summary = (execution.summary + "\n" + reason).strip() if execution.summary else reason

    storage.save_execution(execution)
    ui.warning("执行已暂停")
    ui.print_execution_status(execution)


@app.command("resume")
def resume_execution(
    execution_id: Optional[str] = typer.Option(None, "--id", help="执行ID（默认当前暂停的）"),
):
    """恢复执行"""
    execution = storage.load_execution(execution_id) if execution_id else storage.get_active_execution()
    if execution is None:
        ui.error("暂无暂停的执行会话")
        raise typer.Exit(1)

    if execution.status != ExecutionStatus.PAUSED:
        ui.warning(f"当前状态为 '{execution.status.value}'，无需恢复")
        return

    execution.status = ExecutionStatus.RUNNING
    execution.paused_at = None

    storage.save_execution(execution)
    ui.success("已恢复执行")
    ui.print_execution_status(execution)


@app.command("finish")
def finish_execution(
    summary: str = typer.Option("", "--summary", "-s", help="处理总结"),
    force: bool = typer.Option(False, "--force", "-f", help="忽略未完成步骤，强制结束"),
    execution_id: Optional[str] = typer.Option(None, "--id", help="执行ID（默认当前进行中的）"),
):
    """手动结束执行会话"""
    execution = storage.load_execution(execution_id) if execution_id else storage.get_active_execution()
    if execution is None:
        ui.error("暂无进行中的执行会话")
        raise typer.Exit(1)

    if execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
        ui.info(f"执行会话已结束（状态: {execution.status.value}）")
        return

    pending = [s for s in execution.steps if s.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS)]
    if pending and not force:
        ui.warning(f"还有 {len(pending)} 个步骤未处理")
        for s in pending:
            idx = execution.steps.index(s) + 1
            ui.info(f"  步骤 {idx}: {s.title} [{s.status.value}]")
        if not ui.confirm("仍然结束执行？", default=False):
            return

    now = datetime.now()
    for step in execution.steps:
        if step.status == StepStatus.IN_PROGRESS:
            step.status = StepStatus.SKIPPED
            step.completed_at = now

    has_failed = any(s.status == StepStatus.FAILED for s in execution.steps)
    execution.status = ExecutionStatus.FAILED if has_failed else ExecutionStatus.COMPLETED
    execution.completed_at = now
    if summary:
        execution.summary = (execution.summary + "\n" + summary).strip() if execution.summary else summary

    storage.save_execution(execution)
    ui.success("执行会话已结束")
    ui.print_execution_status(execution)
    if execution.summary:
        ui.info(f"处理总结: {execution.summary}")


@app.command("abort")
def abort_execution(
    reason: str = typer.Option("", "--reason", "-r", help="中止原因"),
    execution_id: Optional[str] = typer.Option(None, "--id", help="执行ID（默认当前进行中的）"),
):
    """中止执行（标记为失败）"""
    execution = storage.load_execution(execution_id) if execution_id else storage.get_active_execution()
    if execution is None:
        ui.error("暂无进行中的执行会话")
        raise typer.Exit(1)

    if execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
        ui.info(f"执行会话已结束（状态: {execution.status.value}）")
        return

    if not ui.confirm("确定中止执行？所有未完成步骤将标记为失败", default=False):
        return

    now = datetime.now()
    for step in execution.steps:
        if step.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS):
            step.status = StepStatus.FAILED
            step.completed_at = now

    execution.status = ExecutionStatus.FAILED
    execution.completed_at = now
    if reason:
        execution.summary = (execution.summary + "\n" + reason).strip() if execution.summary else reason

    storage.save_execution(execution)
    ui.error("执行会话已中止")
    ui.print_execution_status(execution)


@app.command("current")
def show_current():
    """查看当前执行会话的快捷方式（等同 exec status）"""
    execution = storage.get_active_execution()
    if execution is None:
        ui.warning("暂无进行中的执行会话")
        return
    ui.print_execution_status(execution)
