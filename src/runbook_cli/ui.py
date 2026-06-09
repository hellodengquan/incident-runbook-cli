from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .models import (
    ExecutionRecord,
    ExecutionStatus,
    ExecutionStep,
    Runbook,
    RunbookStatus,
    SeverityLevel,
    StepStatus,
)

console = Console()

STATUS_COLORS = {
    StepStatus.PENDING: "dim",
    StepStatus.IN_PROGRESS: "yellow",
    StepStatus.COMPLETED: "green",
    StepStatus.SKIPPED: "blue",
    StepStatus.FAILED: "red",
}

EXEC_STATUS_COLORS = {
    ExecutionStatus.NOT_STARTED: "dim",
    ExecutionStatus.RUNNING: "yellow",
    ExecutionStatus.PAUSED: "magenta",
    ExecutionStatus.COMPLETED: "green",
    ExecutionStatus.FAILED: "red",
}

RUNBOOK_STATUS_COLORS = {
    RunbookStatus.DRAFT: "dim",
    RunbookStatus.ACTIVE: "green",
    RunbookStatus.ARCHIVED: "blue",
}

SEVERITY_COLORS = {
    SeverityLevel.LOW: "blue",
    SeverityLevel.MEDIUM: "yellow",
    SeverityLevel.HIGH: "orange1",
    SeverityLevel.CRITICAL: "red",
}


def format_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_duration(started: Optional[datetime], completed: Optional[datetime]) -> str:
    if started is None:
        return "-"
    end = completed or datetime.now()
    delta = end - started
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def colored_status(status: StepStatus) -> Text:
    color = STATUS_COLORS.get(status, "white")
    status_map = {
        StepStatus.PENDING: "待执行",
        StepStatus.IN_PROGRESS: "执行中",
        StepStatus.COMPLETED: "已完成",
        StepStatus.SKIPPED: "已跳过",
        StepStatus.FAILED: "失败",
    }
    return Text(status_map.get(status, status.value), style=color)


def colored_exec_status(status: ExecutionStatus) -> Text:
    color = EXEC_STATUS_COLORS.get(status, "white")
    status_map = {
        ExecutionStatus.NOT_STARTED: "未开始",
        ExecutionStatus.RUNNING: "进行中",
        ExecutionStatus.PAUSED: "已暂停",
        ExecutionStatus.COMPLETED: "已完成",
        ExecutionStatus.FAILED: "失败",
    }
    return Text(status_map.get(status, status.value), style=color)


def colored_runbook_status(status: RunbookStatus) -> Text:
    color = RUNBOOK_STATUS_COLORS.get(status, "white")
    status_map = {
        RunbookStatus.DRAFT: "草稿",
        RunbookStatus.ACTIVE: "启用",
        RunbookStatus.ARCHIVED: "归档",
    }
    return Text(status_map.get(status, status.value), style=color)


def colored_severity(severity: SeverityLevel) -> Text:
    color = SEVERITY_COLORS.get(severity, "white")
    severity_map = {
        SeverityLevel.LOW: "低",
        SeverityLevel.MEDIUM: "中",
        SeverityLevel.HIGH: "高",
        SeverityLevel.CRITICAL: "严重",
    }
    return Text(severity_map.get(severity, severity.value), style=color)


def print_runbooks_table(runbooks: List[Runbook]) -> None:
    if not runbooks:
        console.print("[yellow]暂无预案，请先使用 create 命令创建[/yellow]")
        return

    table = Table(
        title="预案清单",
        show_lines=False,
        header_style="bold cyan",
        title_style="bold magenta",
    )
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("名称", style="bold white")
    table.add_column("严重级别", justify="center")
    table.add_column("状态", justify="center")
    table.add_column("步骤数", justify="right")
    table.add_column("标签")
    table.add_column("更新时间", no_wrap=True)

    for rb in runbooks:
        tags = ", ".join(rb.tags) if rb.tags else "-"
        table.add_row(
            rb.id,
            rb.name,
            colored_severity(rb.severity),
            colored_runbook_status(rb.status),
            str(len(rb.steps)),
            tags,
            format_datetime(rb.updated_at),
        )

    console.print(table)


def print_runbook_detail(runbook: Runbook) -> None:
    info_lines = [
        f"[bold cyan]ID:[/bold cyan] {runbook.id}",
        f"[bold cyan]名称:[/bold cyan] {runbook.name}",
        f"[bold cyan]严重级别:[/bold cyan] {colored_severity(runbook.severity)}",
        f"[bold cyan]状态:[/bold cyan] {colored_runbook_status(runbook.status)}",
        f"[bold cyan]创建人:[/bold cyan] {runbook.created_by}",
        f"[bold cyan]创建时间:[/bold cyan] {format_datetime(runbook.created_at)}",
        f"[bold cyan]更新时间:[/bold cyan] {format_datetime(runbook.updated_at)}",
    ]
    if runbook.tags:
        info_lines.append(f"[bold cyan]标签:[/bold cyan] {', '.join(runbook.tags)}")
    if runbook.description:
        info_lines.append(f"\n[bold cyan]描述:[/bold cyan]\n{runbook.description}")

    info_panel = Panel(
        "\n".join(info_lines),
        title="预案信息",
        border_style="cyan",
        title_align="left",
    )
    console.print(info_panel)

    if runbook.steps:
        steps_table = Table(
            title="执行步骤",
            show_lines=True,
            header_style="bold green",
            title_style="bold green",
        )
        steps_table.add_column("#", style="dim", justify="right", width=3)
        steps_table.add_column("ID", style="cyan", no_wrap=True)
        steps_table.add_column("步骤名称", style="bold")
        steps_table.add_column("预计时长")
        steps_table.add_column("描述")

        for i, step in enumerate(runbook.steps, 1):
            duration = f"{step.expected_duration_minutes} 分钟" if step.expected_duration_minutes else "-"
            desc_lines = [step.description] if step.description else []
            if step.checklist:
                desc_lines.append("\n[bold]检查项:[/bold]")
                for item in step.checklist:
                    desc_lines.append(f"  • {item}")
            steps_table.add_row(
                str(i),
                step.id,
                step.title,
                duration,
                "\n".join(desc_lines) or "-",
            )
        console.print(steps_table)
    else:
        console.print("[yellow]该预案暂无步骤定义[/yellow]")


def print_execution_status(execution: ExecutionRecord) -> None:
    completed = sum(1 for s in execution.steps if s.status == StepStatus.COMPLETED)
    total = len(execution.steps)
    progress_pct = (completed / total * 100) if total > 0 else 0

    info_lines = [
        f"[bold cyan]执行ID:[/bold cyan] {execution.id}",
        f"[bold cyan]预案:[/bold cyan] {execution.runbook_name} ({execution.runbook_id})",
        f"[bold cyan]严重级别:[/bold cyan] {colored_severity(execution.severity)}",
        f"[bold cyan]状态:[/bold cyan] {colored_exec_status(execution.status)}",
        f"[bold cyan]值班人员:[/bold cyan] {execution.operator}",
        f"[bold cyan]开始时间:[/bold cyan] {format_datetime(execution.started_at)}",
        f"[bold cyan]耗时:[/bold cyan] {format_duration(execution.started_at, execution.completed_at)}",
        f"[bold cyan]进度:[/bold cyan] {completed}/{total} ({progress_pct:.0f}%)",
    ]
    if execution.incident_id:
        info_lines.append(f"[bold cyan]事件ID:[/bold cyan] {execution.incident_id}")
    if execution.paused_at:
        info_lines.append(f"[bold cyan]暂停时间:[/bold cyan] {format_datetime(execution.paused_at)}")

    info_panel = Panel(
        "\n".join(info_lines),
        title="执行状态",
        border_style="magenta",
        title_align="left",
    )
    console.print(info_panel)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )
    with progress:
        task = progress.add_task("整体进度", total=total or 1)
        progress.update(task, completed=completed)

    if execution.steps:
        steps_table = Table(
            show_lines=False,
            header_style="bold yellow",
        )
        steps_table.add_column("#", style="dim", justify="right", width=3)
        steps_table.add_column("状态")
        steps_table.add_column("步骤名称", style="bold")
        steps_table.add_column("操作人")
        steps_table.add_column("开始时间", no_wrap=True)
        steps_table.add_column("完成时间", no_wrap=True)
        steps_table.add_column("备注")

        for i, step in enumerate(execution.steps, 1):
            notes = step.notes or "-"
            if len(notes) > 30:
                notes = notes[:27] + "..."
            steps_table.add_row(
                str(i),
                colored_status(step.status),
                step.title,
                step.operator or "-",
                format_datetime(step.started_at),
                format_datetime(step.completed_at),
                notes,
            )
        console.print(steps_table)


def print_executions_table(executions: List[ExecutionRecord]) -> None:
    if not executions:
        console.print("[yellow]暂无执行记录[/yellow]")
        return

    table = Table(
        title="执行历史",
        show_lines=False,
        header_style="bold cyan",
        title_style="bold magenta",
    )
    table.add_column("执行ID", style="cyan", no_wrap=True)
    table.add_column("预案名称", style="bold")
    table.add_column("严重级别", justify="center")
    table.add_column("状态", justify="center")
    table.add_column("进度", justify="right")
    table.add_column("值班人")
    table.add_column("开始时间", no_wrap=True)
    table.add_column("耗时", no_wrap=True)

    for exec_record in executions:
        completed = sum(1 for s in exec_record.steps if s.status == StepStatus.COMPLETED)
        total = len(exec_record.steps)
        progress = f"{completed}/{total}"
        table.add_row(
            exec_record.id,
            exec_record.runbook_name,
            colored_severity(exec_record.severity),
            colored_exec_status(exec_record.status),
            progress,
            exec_record.operator,
            format_datetime(exec_record.started_at),
            format_duration(exec_record.started_at, exec_record.completed_at),
        )

    console.print(table)


def print_execution_detail(execution: ExecutionRecord) -> None:
    print_execution_status(execution)

    if execution.summary:
        summary_panel = Panel(
            execution.summary,
            title="处理总结",
            border_style="green",
            title_align="left",
        )
        console.print(summary_panel)

    for i, step in enumerate(execution.steps, 1):
        status_text = colored_status(step.status)
        header = f"[bold]步骤 {i}: {step.title}[/bold]  [{status_text}]"
        step_content = []
        if step.started_at:
            step_content.append(f"[cyan]开始:[/cyan] {format_datetime(step.started_at)}")
        if step.completed_at:
            step_content.append(f"[cyan]完成:[/cyan] {format_datetime(step.completed_at)}")
            step_content.append(
                f"[cyan]耗时:[/cyan] {format_duration(step.started_at, step.completed_at)}"
            )
        if step.operator:
            step_content.append(f"[cyan]操作人:[/cyan] {step.operator}")
        if step.notes:
            step_content.append(f"\n[cyan]操作备注:[/cyan]\n{step.notes}")

        panel = Panel(
            "\n".join(step_content) or "暂无详细信息",
            title=header,
            border_style="blue",
            title_align="left",
        )
        console.print(panel)


def confirm(prompt: str, default: bool = False) -> bool:
    return Confirm.ask(prompt, default=default)


def prompt_input(prompt: str, default: Optional[str] = None, password: bool = False) -> str:
    kwargs = {"password": password}
    if default is not None:
        kwargs["default"] = default
    return Prompt.ask(prompt, **kwargs)


def success(message: str) -> None:
    console.print(f"[green]✓ {message}[/green]")


def error(message: str) -> None:
    console.print(f"[red]✗ {message}[/red]")


def warning(message: str) -> None:
    console.print(f"[yellow]⚠ {message}[/yellow]")


def info(message: str) -> None:
    console.print(f"[blue]ℹ {message}[/blue]")
