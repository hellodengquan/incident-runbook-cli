from __future__ import annotations

from typing import List, Optional

import typer

from ..models import Runbook, RunbookStatus, SeverityLevel, Step
from ..storage import RunbookStorage
from .. import ui

app = typer.Typer(help="预案清单管理命令", no_args_is_help=True)
storage = RunbookStorage()


@app.command("create")
def create_runbook(
    name: str = typer.Option(..., "--name", "-n", help="预案名称"),
    description: str = typer.Option("", "--description", "-d", help="预案描述"),
    severity: SeverityLevel = typer.Option(
        SeverityLevel.MEDIUM, "--severity", "-s", help="严重级别"
    ),
    tags: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="标签（可多次指定）"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="交互模式"),
    created_by: str = typer.Option("oncall", "--created-by", help="创建人"),
):
    """创建新预案"""
    if interactive:
        ui.info("交互模式创建预案（输入空白使用默认值）")
        if not name:
            name = ui.prompt_input("预案名称")
        if not description:
            description = ui.prompt_input("预案描述（可留空）", default="")
        severity_str = ui.prompt_input(
            f"严重级别 (low/medium/high/critical) [默认: {severity.value}]",
            default=severity.value,
        )
        try:
            severity = SeverityLevel(severity_str.lower())
        except ValueError:
            ui.warning(f"无效的严重级别，使用默认值: {severity.value}")

    if not name:
        ui.error("预案名称不能为空")
        raise typer.Exit(1)

    existing = storage.find_runbook_by_name(name)
    if existing:
        ui.warning(f"已存在同名预案: {existing.id}")
        if not ui.confirm("是否继续创建？", default=False):
            raise typer.Exit(0)

    runbook = Runbook(
        name=name,
        description=description,
        severity=severity,
        tags=tags or [],
        created_by=created_by,
    )

    if interactive:
        ui.info("开始定义执行步骤（输入空白步骤名称结束）")
        step_index = 1
        while True:
            title = ui.prompt_input(f"步骤 {step_index} 名称", default="")
            if not title:
                break
            desc = ui.prompt_input(f"步骤 {step_index} 描述（可留空）", default="")
            duration_str = ui.prompt_input("预计时长（分钟，可留空）", default="")
            duration = int(duration_str) if duration_str.isdigit() else None

            checklist_items = []
            add_checklist = ui.confirm("是否添加检查项？", default=False)
            if add_checklist:
                ci = 1
                while True:
                    item = ui.prompt_input(f"检查项 {ci}", default="")
                    if not item:
                        break
                    checklist_items.append(item)
                    ci += 1

            step = Step(
                title=title,
                description=desc,
                expected_duration_minutes=duration,
                checklist=checklist_items,
            )
            runbook.steps.append(step)
            step_index += 1

        ui.info(f"共定义 {len(runbook.steps)} 个步骤")

    storage.save_runbook(runbook)
    ui.success(f"预案创建成功: {runbook.id}")
    ui.print_runbook_detail(runbook)


@app.command("list")
def list_runbooks(
    status: Optional[RunbookStatus] = typer.Option(None, "--status", help="按状态过滤"),
    severity: Optional[SeverityLevel] = typer.Option(None, "--severity", help="按严重级别过滤"),
    tag: Optional[str] = typer.Option(None, "--tag", help="按标签过滤"),
):
    """列出所有预案"""
    runbooks = storage.list_runbooks()

    if status:
        runbooks = [r for r in runbooks if r.status == status]
    if severity:
        runbooks = [r for r in runbooks if r.severity == severity]
    if tag:
        runbooks = [r for r in runbooks if tag in r.tags]

    ui.print_runbooks_table(runbooks)


@app.command("show")
def show_runbook(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
):
    """查看预案详情"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)
    ui.print_runbook_detail(runbook)


@app.command("delete")
def delete_runbook(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
    force: bool = typer.Option(False, "--force", "-f", help="不提示直接删除"),
):
    """删除预案"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    ui.print_runbook_detail(runbook)

    if not force:
        if not ui.confirm(f"确定要删除预案 '{runbook.name}' 吗？此操作不可撤销", default=False):
            ui.info("已取消删除")
            raise typer.Exit(0)

    storage.delete_runbook(runbook.id)
    ui.success(f"预案已删除: {runbook.id}")


@app.command("edit")
def edit_runbook(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="新名称"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="新描述"),
    severity: Optional[SeverityLevel] = typer.Option(None, "--severity", "-s", help="新严重级别"),
    status: Optional[RunbookStatus] = typer.Option(None, "--status", help="新状态"),
    add_tag: Optional[List[str]] = typer.Option(None, "--add-tag", help="添加标签"),
    remove_tag: Optional[List[str]] = typer.Option(None, "--remove-tag", help="移除标签"),
):
    """编辑预案基本信息"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    updated = False
    if name:
        runbook.name = name
        updated = True
    if description is not None:
        runbook.description = description
        updated = True
    if severity:
        runbook.severity = severity
        updated = True
    if status:
        runbook.status = status
        updated = True
    if add_tag:
        for t in add_tag:
            if t not in runbook.tags:
                runbook.tags.append(t)
                updated = True
    if remove_tag:
        for t in remove_tag:
            if t in runbook.tags:
                runbook.tags.remove(t)
                updated = True

    if not updated:
        ui.info("未指定任何修改项")
        return

    storage.save_runbook(runbook)
    ui.success("预案信息已更新")
    ui.print_runbook_detail(runbook)


@app.command("add-step")
def add_step(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
    title: str = typer.Option(..., "--title", "-t", help="步骤名称"),
    description: str = typer.Option("", "--description", "-d", help="步骤描述"),
    duration: Optional[int] = typer.Option(None, "--duration", help="预计时长（分钟）"),
    position: Optional[int] = typer.Option(None, "--position", "-p", help="插入位置（从1开始，默认末尾）"),
):
    """向预案添加执行步骤"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    step = Step(
        title=title,
        description=description,
        expected_duration_minutes=duration,
    )

    if position is not None and position > 0:
        idx = min(position - 1, len(runbook.steps))
        runbook.steps.insert(idx, step)
    else:
        runbook.steps.append(step)

    storage.save_runbook(runbook)
    ui.success(f"步骤已添加，当前共 {len(runbook.steps)} 个步骤")
    ui.print_runbook_detail(runbook)


@app.command("remove-step")
def remove_step(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
    step_ref: str = typer.Argument(..., help="步骤编号（从1开始）或步骤ID"),
    force: bool = typer.Option(False, "--force", "-f", help="不提示直接删除"),
):
    """从预案移除执行步骤"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    if not runbook.steps:
        ui.warning("预案暂无步骤")
        return

    target_idx = None
    if step_ref.isdigit():
        idx = int(step_ref) - 1
        if 0 <= idx < len(runbook.steps):
            target_idx = idx
    else:
        for i, step in enumerate(runbook.steps):
            if step.id == step_ref:
                target_idx = i
                break

    if target_idx is None:
        ui.error(f"步骤不存在: {step_ref}")
        raise typer.Exit(1)

    step = runbook.steps[target_idx]
    ui.info(f"将要删除步骤 {target_idx + 1}: {step.title}")

    if not force:
        if not ui.confirm("确定删除该步骤？", default=False):
            ui.info("已取消")
            return

    runbook.steps.pop(target_idx)
    storage.save_runbook(runbook)
    ui.success("步骤已删除")
    ui.print_runbook_detail(runbook)


@app.command("activate")
def activate_runbook(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
):
    """激活预案（状态改为 active）"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    if not runbook.steps:
        ui.warning("预案没有定义步骤，建议先添加步骤再激活")
        if not ui.confirm("仍然激活？", default=False):
            return

    runbook.status = RunbookStatus.ACTIVE
    storage.save_runbook(runbook)
    ui.success(f"预案已激活: {runbook.name}")


@app.command("archive")
def archive_runbook(
    runbook_id: str = typer.Argument(..., help="预案ID或名称"),
):
    """归档预案"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    runbook.status = RunbookStatus.ARCHIVED
    storage.save_runbook(runbook)
    ui.success(f"预案已归档: {runbook.name}")


@app.command("copy")
def copy_runbook(
    runbook_id: str = typer.Argument(..., help="源预案ID或名称"),
    new_name: str = typer.Option(..., "--name", "-n", help="新预案名称"),
):
    """复制（克隆）预案"""
    runbook = storage.load_runbook(runbook_id)
    if runbook is None:
        runbook = storage.find_runbook_by_name(runbook_id)
    if runbook is None:
        ui.error(f"预案不存在: {runbook_id}")
        raise typer.Exit(1)

    new_runbook = Runbook(
        name=new_name,
        description=runbook.description,
        severity=runbook.severity,
        status=RunbookStatus.DRAFT,
        steps=[Step(**s.model_dump()) for s in runbook.steps],
        tags=list(runbook.tags),
        created_by=runbook.created_by,
    )

    storage.save_runbook(new_runbook)
    ui.success(f"预案已复制，新ID: {new_runbook.id}")
    ui.print_runbook_detail(new_runbook)
