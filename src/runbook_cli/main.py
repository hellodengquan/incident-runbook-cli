from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from . import __version__, ui
from .commands.runbook_cmds import app as runbook_app
from .commands.exec_cmds import app as exec_app
from .commands.history_cmds import app as history_app
from .commands.admin_cmds import app as admin_app
from .storage import RunbookStorage

app = typer.Typer(
    name="runbook",
    help="应急 Runbook CLI 工具 - 值班期间预案管理与执行追踪",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

app.add_typer(runbook_app, name="runbook", help="预案清单管理（创建/查看/编辑/删除）")
app.add_typer(exec_app, name="exec", help="执行追踪（开始/步骤/暂停/恢复）")
app.add_typer(history_app, name="history", help="历史记录（回顾/统计/导出）")
app.add_typer(admin_app, name="admin", help="运维管理（锁清理/诊断）")

storage = RunbookStorage()


def _version_callback(value: bool) -> None:
    if value:
        ui.console.print(f"[bold cyan]runbook-cli[/bold cyan] version [green]{__version__}[/green]")
        ui.console.print(f"[dim]数据目录: {storage.base_dir}[/dim]")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="显示版本信息",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """
    [bold]应急 Runbook CLI 工具[/bold]

    值班期间用于管理应急预案、追踪执行步骤、回顾处理记录。

    \n\n[bold]主要功能:[/bold]\n
    • [cyan]runbook[/cyan]   预案清单管理（create/list/show/edit/delete）\n
    • [cyan]exec[/cyan]      执行状态追踪（start/step/status/pause/resume）\n
    • [cyan]history[/cyan]   处理记录回顾（list/show/summary/export）

    \n\n[bold]常用示例:[/bold]\n
    $ runbook runbook create --name "数据库故障恢复" --interactive\n
    $ runbook exec start "数据库故障恢复"\n
    $ runbook exec step start 1\n
    $ runbook exec step complete --notes "已确认连接恢复"\n
    $ runbook exec status\n
    $ runbook history summary --last-days 7
    """
    return


@app.command("dashboard")
def dashboard():
    """总览仪表板：显示当前状态与统计"""
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table

    ui.console.rule("[bold magenta]应急 Runbook 仪表板[/bold magenta]")

    active = storage.get_active_execution()
    runbooks = storage.list_runbooks()
    executions = storage.list_executions()

    layout = Layout()
    layout.split_column(
        Layout(name="upper"),
        Layout(name="lower"),
    )
    layout["upper"].split_row(
        Layout(name="active"),
        Layout(name="stats"),
    )

    active_lines = []
    if active:
        from .models import ExecutionStatus, StepStatus

        completed = sum(1 for s in active.steps if s.status == StepStatus.COMPLETED)
        total = len(active.steps)
        active_lines.append(f"[bold]执行ID:[/bold] {active.id}")
        active_lines.append(f"[bold]预案:[/bold] {active.runbook_name}")
        active_lines.append(f"[bold]状态:[/bold] {ui.colored_exec_status(active.status)}")
        active_lines.append(f"[bold]值班人:[/bold] {active.operator}")
        active_lines.append(f"[bold]开始时间:[/bold] {ui.format_datetime(active.started_at)}")
        active_lines.append(f"[bold]进度:[/bold] {completed}/{total}")
        active_lines.append("")
        active_lines.append("[bold]当前步骤:[/bold]")
        for i, step in enumerate(active.steps, 1):
            marker = ""
            if step.status == StepStatus.IN_PROGRESS:
                marker = "[yellow]▶[/yellow] "
            elif step.status == StepStatus.COMPLETED:
                marker = "[green]✓[/green] "
            elif step.status == StepStatus.FAILED:
                marker = "[red]✗[/red] "
            elif step.status == StepStatus.SKIPPED:
                marker = "[blue]→[/blue] "
            else:
                marker = "[dim]○[/dim] "
            active_lines.append(f"  {marker}{i}. {step.title}")
        active_title = "进行中的执行"
        active_border = "yellow"
    else:
        active_lines.append("[dim]暂无进行中的执行会话[/dim]")
        active_lines.append("")
        active_lines.append("使用 [cyan]runbook exec start <预案ID>[/cyan] 开始执行")
        active_title = "当前执行"
        active_border = "dim"

    layout["active"].update(
        Panel("\n".join(active_lines), title=active_title, border_style=active_border, title_align="left")
    )

    total_rb = len(runbooks)
    from .models import RunbookStatus
    active_rb = sum(1 for r in runbooks if r.status == RunbookStatus.ACTIVE)
    draft_rb = sum(1 for r in runbooks if r.status == RunbookStatus.DRAFT)
    archived_rb = sum(1 for r in runbooks if r.status == RunbookStatus.ARCHIVED)

    from .models import ExecutionStatus
    total_ex = len(executions)
    completed_ex = sum(1 for e in executions if e.status == ExecutionStatus.COMPLETED)
    failed_ex = sum(1 for e in executions if e.status == ExecutionStatus.FAILED)
    today_ex = 0
    from datetime import datetime
    today = datetime.now().date()
    for e in executions:
        if e.started_at and e.started_at.date() == today:
            today_ex += 1

    stats_lines = [
        f"[bold cyan]预案总数:[/bold cyan] {total_rb}",
        f"  [green]启用:[/green] {active_rb}  [dim]草稿:[/dim] {draft_rb}  [blue]归档:[/blue] {archived_rb}",
        "",
        f"[bold cyan]执行总数:[/bold cyan] {total_ex}",
        f"  [green]成功:[/green] {completed_ex}  [red]失败:[/red] {failed_ex}  [yellow]今日:[/yellow] {today_ex}",
        "",
        f"[dim]数据目录: {storage.base_dir}[/dim]",
    ]
    layout["stats"].update(
        Panel("\n".join(stats_lines), title="数据统计", border_style="cyan", title_align="left")
    )

    recent = executions[:5]
    if recent:
        table = Table(
            title="最近执行记录",
            show_lines=False,
            header_style="bold blue",
            title_style="bold blue",
        )
        table.add_column("执行ID", style="cyan")
        table.add_column("预案名称", style="bold")
        table.add_column("状态")
        table.add_column("值班人")
        table.add_column("开始时间")
        table.add_column("耗时")

        from .models import StepStatus
        for e in recent:
            comp = sum(1 for s in e.steps if s.status == StepStatus.COMPLETED)
            total = len(e.steps)
            prog = f" {comp}/{total}" if total else ""
            table.add_row(
                e.id,
                e.runbook_name + prog,
                ui.colored_exec_status(e.status),
                e.operator,
                ui.format_datetime(e.started_at),
                ui.format_duration(e.started_at, e.completed_at),
            )
        layout["lower"].update(table)
    else:
        layout["lower"].update(
            Panel("[yellow]暂无执行记录[/yellow]", title="最近执行", border_style="dim")
        )

    ui.console.print(layout)
    ui.console.rule()


@app.command("init-demo")
def init_demo(
    force: bool = typer.Option(False, "--force", "-f", help="已存在数据时强制覆盖"),
):
    """初始化示例数据（演示用）"""
    from .models import Runbook, RunbookStatus, SeverityLevel, Step

    existing = storage.list_runbooks()
    if existing and not force:
        ui.warning(f"已存在 {len(existing)} 个预案")
        if not ui.confirm("仍要添加示例数据？", default=False):
            return

    demos = [
        Runbook(
            name="MySQL 主库故障切换",
            description="MySQL 主库不可用时的主从切换操作流程，保障数据库服务连续性",
            severity=SeverityLevel.CRITICAL,
            status=RunbookStatus.ACTIVE,
            tags=["数据库", "MySQL", "高可用"],
            created_by="demo",
            steps=[
                Step(
                    title="确认主库故障状态",
                    description="通过监控和连接测试确认主库确实不可用",
                    expected_duration_minutes=5,
                    checklist=[
                        "检查监控告警确认主库宕机",
                        "尝试 telnet 3306 端口确认",
                        "尝试 mysql 客户端连接确认",
                    ],
                ),
                Step(
                    title="通知相关干系人",
                    description="通过电话和即时通讯工具通知 DBA 和业务负责人",
                    expected_duration_minutes=3,
                    checklist=[
                        "电话通知 DBA 值班人员",
                        "微信群/钉钉群发布故障通知",
                        "记录通知时间点",
                    ],
                ),
                Step(
                    title="选择新主库候选",
                    description="检查从库状态，选择数据最新的从库作为新主",
                    expected_duration_minutes=5,
                    checklist=[
                        "检查所有从库的 Seconds_Behind_Master",
                        "确认从库数据一致性",
                        "选择延迟最小的从库",
                    ],
                ),
                Step(
                    title="执行主从切换",
                    description="在候选从库上执行提升操作",
                    expected_duration_minutes=10,
                    checklist=[
                        "STOP SLAVE",
                        "RESET MASTER",
                        "执行应用配置变更指向新主",
                    ],
                ),
                Step(
                    title="验证业务恢复",
                    description="确认业务读写正常",
                    expected_duration_minutes=5,
                    checklist=[
                        "连接测试确认可写入",
                        "核心业务接口冒烟测试",
                        "观察监控指标恢复正常",
                    ],
                ),
                Step(
                    title="故障复盘记录",
                    description="记录故障根因和处理过程用于复盘",
                    expected_duration_minutes=10,
                ),
            ],
        ),
        Runbook(
            name="Kubernetes 节点异常处理",
            description="K8s 集群节点 NotReady 时的排查与处理流程",
            severity=SeverityLevel.HIGH,
            status=RunbookStatus.ACTIVE,
            tags=["Kubernetes", "容器", "基础设施"],
            created_by="demo",
            steps=[
                Step(
                    title="确认节点状态",
                    description="kubectl 查看节点状态及相关事件",
                    expected_duration_minutes=3,
                    checklist=[
                        "kubectl get nodes",
                        "kubectl describe node <node-name>",
                        "确认节点 NotReady 持续时间",
                    ],
                ),
                Step(
                    title="疏散异常节点上的 Pod",
                    description="对异常节点执行 cordon 和 drain",
                    expected_duration_minutes=5,
                ),
                Step(
                    title="排查节点故障",
                    description="SSH 登录节点检查 kubelet、docker、网络等",
                    expected_duration_minutes=10,
                    checklist=[
                        "systemctl status kubelet",
                        "journalctl -u kubelet 查日志",
                        "检查磁盘/内存/CPU 使用率",
                        "检查网络连通性",
                    ],
                ),
                Step(
                    title="修复或替换节点",
                    description="根据排查结果进行修复或直接替换",
                    expected_duration_minutes=15,
                ),
                Step(
                    title="恢复节点",
                    description="节点恢复正常后执行 uncordon",
                    expected_duration_minutes=3,
                ),
            ],
        ),
        Runbook(
            name="线上服务 OOM 处理",
            description="Java/Python 等服务发生 OOM 时的标准处理流程",
            severity=SeverityLevel.MEDIUM,
            status=RunbookStatus.DRAFT,
            tags=["应用", "内存", "性能"],
            created_by="demo",
            steps=[
                Step(title="获取内存快照", description="jmap/gcore 抓取堆转储或 coredump"),
                Step(title="重启服务实例", description="滚动重启恢复服务"),
                Step(title="分析内存泄漏", description="MAT/JProfiler 分析内存快照"),
                Step(title="定位并修复根因", description="代码层面修复问题"),
                Step(title="验证修复效果", description="压测确认内存正常"),
            ],
        ),
    ]

    for rb in demos:
        storage.save_runbook(rb)
        ui.success(f"已添加示例预案: {rb.name}")

    ui.info("示例数据初始化完成")
    ui.print_runbooks_table(storage.list_runbooks())
