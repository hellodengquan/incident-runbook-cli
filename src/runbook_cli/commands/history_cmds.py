from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer

from ..models import ExecutionStatus, SeverityLevel, StepStatus
from ..storage import RunbookStorage
from .. import ui

app = typer.Typer(help="处理记录回顾与导出", no_args_is_help=True)
storage = RunbookStorage()


@app.command("list")
def list_history(
    runbook_id: Optional[str] = typer.Option(None, "--runbook", "-r", help="按预案ID或名称过滤"),
    status: Optional[ExecutionStatus] = typer.Option(None, "--status", "-s", help="按执行状态过滤"),
    severity: Optional[SeverityLevel] = typer.Option(None, "--severity", help="按严重级别过滤"),
    operator: Optional[str] = typer.Option(None, "--operator", "-o", help="按值班人员过滤"),
    last_days: Optional[int] = typer.Option(None, "--last-days", help="仅显示最近N天的记录"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="最多显示N条记录"),
):
    """列出执行历史记录"""
    executions = storage.list_executions()

    if runbook_id:
        runbook = storage.load_runbook(runbook_id)
        if runbook is None:
            runbook = storage.find_runbook_by_name(runbook_id)
        if runbook:
            runbook_id = runbook.id
        executions = [e for e in executions if e.runbook_id == runbook_id]

    if status:
        executions = [e for e in executions if e.status == status]
    if severity:
        executions = [e for e in executions if e.severity == severity]
    if operator:
        executions = [e for e in executions if e.operator == operator]
    if last_days:
        cutoff = datetime.now() - timedelta(days=last_days)
        executions = [
            e for e in executions
            if e.started_at and e.started_at >= cutoff
        ]
    if limit:
        executions = executions[:limit]

    ui.print_executions_table(executions)


@app.command("show")
def show_history_detail(
    execution_id: str = typer.Argument(..., help="执行ID"),
):
    """查看某次执行的完整详情"""
    execution = storage.load_execution(execution_id)
    if execution is None:
        ui.error(f"执行记录不存在: {execution_id}")
        raise typer.Exit(1)

    ui.print_execution_detail(execution)


@app.command("export")
def export_record(
    execution_id: str = typer.Argument(..., help="执行ID"),
    format: str = typer.Option(
        "json", "--format", "-f", help="导出格式: json, md (markdown), txt"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件路径"),
):
    """导出执行记录为文件"""
    execution = storage.load_execution(execution_id)
    if execution is None:
        ui.error(f"执行记录不存在: {execution_id}")
        raise typer.Exit(1)

    format = format.lower()
    if format not in ("json", "md", "markdown", "txt"):
        ui.error(f"不支持的格式: {format}（支持: json, md, txt）")
        raise typer.Exit(1)

    if format == "json":
        content = execution.model_dump_json(indent=2)
        default_suffix = ".json"
    elif format in ("md", "markdown"):
        content = _render_markdown(execution)
        default_suffix = ".md"
    else:
        content = _render_text(execution)
        default_suffix = ".txt"

    if output is None:
        ts = (execution.started_at or datetime.now()).strftime("%Y%m%d-%H%M%S")
        output = Path.cwd() / f"runbook-{execution.runbook_name}-{ts}{default_suffix}"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    ui.success(f"已导出到: {output}")


def _render_markdown(execution) -> str:
    lines = []
    lines.append(f"# 应急处理记录 - {execution.runbook_name}")
    lines.append("")
    lines.append("## 基本信息")
    lines.append("")
    lines.append(f"- **执行ID**: {execution.id}")
    lines.append(f"- **预案ID**: {execution.runbook_id}")
    lines.append(f"- **严重级别**: {execution.severity.value}")
    lines.append(f"- **执行状态**: {execution.status.value}")
    lines.append(f"- **值班人员**: {execution.operator}")
    if execution.incident_id:
        lines.append(f"- **事件ID**: {execution.incident_id}")
    lines.append(f"- **开始时间**: {ui.format_datetime(execution.started_at)}")
    lines.append(f"- **结束时间**: {ui.format_datetime(execution.completed_at)}")
    lines.append(f"- **总耗时**: {ui.format_duration(execution.started_at, execution.completed_at)}")
    lines.append("")

    completed = sum(1 for s in execution.steps if s.status == StepStatus.COMPLETED)
    total = len(execution.steps)
    lines.append("## 执行摘要")
    lines.append("")
    lines.append(f"- 总步骤数: {total}")
    lines.append(f"- 已完成: {completed}")
    lines.append(f"- 已跳过: {sum(1 for s in execution.steps if s.status == StepStatus.SKIPPED)}")
    lines.append(f"- 失败: {sum(1 for s in execution.steps if s.status == StepStatus.FAILED)}")
    lines.append(f"- 待执行: {sum(1 for s in execution.steps if s.status == StepStatus.PENDING)}")
    lines.append("")

    if execution.summary:
        lines.append("## 处理总结")
        lines.append("")
        lines.append(execution.summary)
        lines.append("")

    lines.append("## 执行步骤详情")
    lines.append("")
    for i, step in enumerate(execution.steps, 1):
        lines.append(f"### {i}. {step.title}")
        lines.append("")
        lines.append(f"- **步骤ID**: {step.step_id}")
        lines.append(f"- **状态**: {step.status.value}")
        lines.append(f"- **操作人**: {step.operator or '-'}")
        lines.append(f"- **开始时间**: {ui.format_datetime(step.started_at)}")
        lines.append(f"- **完成时间**: {ui.format_datetime(step.completed_at)}")
        if step.started_at and step.completed_at:
            lines.append(f"- **耗时**: {ui.format_duration(step.started_at, step.completed_at)}")
        if step.notes:
            lines.append("")
            lines.append("**操作备注**:")
            lines.append("")
            lines.append("```")
            lines.append(step.notes)
            lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _render_text(execution) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f"应急处理记录 - {execution.runbook_name}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("【基本信息】")
    lines.append(f"  执行ID:     {execution.id}")
    lines.append(f"  预案ID:     {execution.runbook_id}")
    lines.append(f"  严重级别:   {execution.severity.value}")
    lines.append(f"  执行状态:   {execution.status.value}")
    lines.append(f"  值班人员:   {execution.operator}")
    if execution.incident_id:
        lines.append(f"  事件ID:     {execution.incident_id}")
    lines.append(f"  开始时间:   {ui.format_datetime(execution.started_at)}")
    lines.append(f"  结束时间:   {ui.format_datetime(execution.completed_at)}")
    lines.append(f"  总耗时:     {ui.format_duration(execution.started_at, execution.completed_at)}")
    lines.append("")

    completed = sum(1 for s in execution.steps if s.status == StepStatus.COMPLETED)
    total = len(execution.steps)
    lines.append("【执行摘要】")
    lines.append(f"  总步骤数: {total}")
    lines.append(f"  已完成:   {completed}")
    lines.append(f"  已跳过:   {sum(1 for s in execution.steps if s.status == StepStatus.SKIPPED)}")
    lines.append(f"  失败:     {sum(1 for s in execution.steps if s.status == StepStatus.FAILED)}")
    lines.append(f"  待执行:   {sum(1 for s in execution.steps if s.status == StepStatus.PENDING)}")
    lines.append("")

    if execution.summary:
        lines.append("【处理总结】")
        lines.append(f"  {execution.summary}")
        lines.append("")

    lines.append("【执行步骤详情】")
    lines.append("-" * 60)
    for i, step in enumerate(execution.steps, 1):
        lines.append("")
        lines.append(f"  {i}. {step.title}  [{step.status.value}]")
        lines.append(f"     步骤ID:   {step.step_id}")
        lines.append(f"     操作人:   {step.operator or '-'}")
        lines.append(f"     开始时间: {ui.format_datetime(step.started_at)}")
        lines.append(f"     完成时间: {ui.format_datetime(step.completed_at)}")
        if step.started_at and step.completed_at:
            lines.append(f"     耗时:     {ui.format_duration(step.started_at, step.completed_at)}")
        if step.notes:
            lines.append(f"     操作备注:")
            for note_line in step.notes.split("\n"):
                lines.append(f"       {note_line}")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


@app.command("summary")
def show_summary(
    last_days: int = typer.Option(30, "--last-days", "-d", help="统计最近N天的数据"),
    runbook_id: Optional[str] = typer.Option(None, "--runbook", "-r", help="按预案过滤"),
):
    """显示执行统计摘要"""
    executions = storage.list_executions()

    if runbook_id:
        runbook = storage.load_runbook(runbook_id)
        if runbook is None:
            runbook = storage.find_runbook_by_name(runbook_id)
        if runbook:
            runbook_id = runbook.id
        executions = [e for e in executions if e.runbook_id == runbook_id]

    cutoff = datetime.now() - timedelta(days=last_days)
    executions = [
        e for e in executions
        if e.started_at and e.started_at >= cutoff
    ]

    if not executions:
        ui.warning(f"最近 {last_days} 天内暂无执行记录")
        return

    total = len(executions)
    completed = sum(1 for e in executions if e.status == ExecutionStatus.COMPLETED)
    failed = sum(1 for e in executions if e.status == ExecutionStatus.FAILED)
    running = sum(1 for e in executions if e.status in (ExecutionStatus.RUNNING, ExecutionStatus.PAUSED))

    total_steps = sum(len(e.steps) for e in executions)
    completed_steps = sum(
        sum(1 for s in e.steps if s.status == StepStatus.COMPLETED)
        for e in executions
    )
    failed_steps = sum(
        sum(1 for s in e.steps if s.status == StepStatus.FAILED)
        for e in executions
    )

    durations = []
    for e in executions:
        if e.started_at and e.completed_at:
            durations.append((e.completed_at - e.started_at).total_seconds())

    from rich.table import Table
    from rich.panel import Panel

    summary_lines = [
        f"[bold cyan]统计周期:[/bold cyan] 最近 {last_days} 天",
        f"[bold cyan]执行总数:[/bold cyan] {total}",
        f"[bold cyan]已完成:[/bold cyan] [green]{completed}[/green]",
        f"[bold cyan]失败:[/bold cyan] [red]{failed}[/red]",
        f"[bold cyan]进行中/暂停:[/bold cyan] [yellow]{running}[/yellow]",
    ]
    if total > 0:
        success_rate = completed / total * 100
        summary_lines.append(f"[bold cyan]成功率:[/bold cyan] {success_rate:.1f}%")
    summary_lines.append("")
    summary_lines.append(f"[bold cyan]步骤总数:[/bold cyan] {total_steps}")
    summary_lines.append(f"[bold cyan]已完成步骤:[/bold cyan] {completed_steps}")
    summary_lines.append(f"[bold cyan]失败步骤:[/bold cyan] {failed_steps}")

    if durations:
        avg_sec = sum(durations) / len(durations)
        max_sec = max(durations)
        min_sec = min(durations)
        summary_lines.append("")
        summary_lines.append(f"[bold cyan]平均耗时:[/bold cyan] {_fmt_sec(avg_sec)}")
        summary_lines.append(f"[bold cyan]最长耗时:[/bold cyan] {_fmt_sec(max_sec)}")
        summary_lines.append(f"[bold cyan]最短耗时:[/bold cyan] {_fmt_sec(min_sec)}")

    panel = Panel(
        "\n".join(summary_lines),
        title=f"执行统计摘要（最近 {last_days} 天）",
        border_style="cyan",
        title_align="left",
    )
    ui.console.print(panel)

    by_runbook: dict[str, dict] = {}
    for e in executions:
        key = f"{e.runbook_name} ({e.runbook_id})"
        if key not in by_runbook:
            by_runbook[key] = {"total": 0, "completed": 0, "failed": 0}
        by_runbook[key]["total"] += 1
        if e.status == ExecutionStatus.COMPLETED:
            by_runbook[key]["completed"] += 1
        elif e.status == ExecutionStatus.FAILED:
            by_runbook[key]["failed"] += 1

    if len(by_runbook) > 1:
        table = Table(
            title="按预案统计",
            show_lines=False,
            header_style="bold green",
            title_style="bold green",
        )
        table.add_column("预案")
        table.add_column("执行次数", justify="right")
        table.add_column("成功", justify="right", style="green")
        table.add_column("失败", justify="right", style="red")
        table.add_column("成功率", justify="right")

        for name, stats in sorted(by_runbook.items(), key=lambda x: -x[1]["total"]):
            rate = stats["completed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            table.add_row(
                name,
                str(stats["total"]),
                str(stats["completed"]),
                str(stats["failed"]),
                f"{rate:.1f}%",
            )
        ui.console.print(table)


def _fmt_sec(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
