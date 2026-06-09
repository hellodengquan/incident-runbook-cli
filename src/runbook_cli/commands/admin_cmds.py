from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from .. import ui
from ..storage import RunbookStorage, STALE_LOCK_MAX_AGE_SECONDS
from ..storage import (
    lock_implementation_class,
    new_platform_lock,
    _pid_alive,
    _read_pid_mark,
)

app = typer.Typer(help="运维管理（锁清理/诊断）", no_args_is_help=True)
storage = RunbookStorage()


def _platform_name() -> str:
    plat = sys.platform.lower()
    if plat == "win32":
        return "windows"
    if plat in ("darwin", "linux", "linux2", "freebsd", "openbsd", "netbsd"):
        return "posix"
    return "unknown"


def _lock_impl_name() -> str:
    return lock_implementation_class(sys.platform).__name__


@app.command("clean-locks")
def clean_locks(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="仅列出将要清理的锁文件，不实际删除",
    ),
    max_age: Optional[int] = typer.Option(
        None,
        "--max-age",
        "-a",
        help=f"锁文件的最大存活秒数（默认 STALE_LOCK_MAX_AGE_SECONDS = {STALE_LOCK_MAX_AGE_SECONDS}）",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="显示每个锁的详细信息"),
):
    """扫描并清理 .locks 目录中的孤儿锁文件"""
    lock_dir = storage._lock_dir
    if not lock_dir.exists():
        ui.warning(f"锁目录不存在: {lock_dir}")
        return

    limit_label = f"{max_age}s" if max_age is not None else f"{STALE_LOCK_MAX_AGE_SECONDS}s (默认)"
    mode_label = "[[bold yellow]DRY-RUN[/bold yellow]]" if dry_run else "[[bold red]CLEAN[/bold red]]"

    ui.console.rule(f"[bold magenta]runbook admin clean-locks[/bold magenta]  {mode_label}")
    ui.info(f"扫描目录: {lock_dir}")
    ui.info(f"年龄阈值: {limit_label}")
    ui.info(f"锁实现: {_lock_impl_name()}  [{_platform_name()}]")
    ui.info("")

    # 手动统计：走和 cleanup_stale_locks 完全相同逻辑但 verbose 打印
    limit = max_age if max_age is not None else STALE_LOCK_MAX_AGE_SECONDS
    now_ts = datetime.now().timestamp()
    lock_files = sorted(lock_dir.glob("*.lock"))
    if not lock_files:
        ui.info("锁目录为空，无需清理")
        return

    to_remove: list[Path] = []
    to_keep: list[Path] = []
    rows = []

    for lock_file in lock_files:
        try:
            mark = _read_pid_mark(lock_file)
            reason = "-"
            status = "keep"
            if mark is None:
                try:
                    st = lock_file.stat()
                    age_s = now_ts - st.st_mtime
                    empty = st.st_size == 0
                except OSError:
                    to_keep.append(lock_file)
                    rows.append((lock_file.name, "-", "-", "-", "ERROR", "-"))
                    continue
                if empty and age_s > limit:
                    status = "stale"
                    reason = f"空文件，age={age_s:.0f}s > {limit}s"
                    to_remove.append(lock_file)
                else:
                    to_keep.append(lock_file)
                age_display = f"{age_s:.0f}s"
                pid_display = "-"
                pid_alive_display = "-"
            else:
                pid, ts = mark
                age_s = now_ts - ts if ts <= now_ts else 0
                age_display = f"{age_s:.0f}s"
                pid_display = str(pid)
                alive = _pid_alive(pid)
                pid_alive_display = "YES" if alive else "NO"
                if not alive or age_s > limit:
                    status = "stale"
                    reasons = []
                    if not alive:
                        reasons.append(f"PID {pid} 已死亡")
                    if age_s > limit:
                        reasons.append(f"age={age_s:.0f}s > {limit}s")
                    reason = ", ".join(reasons)
                    to_remove.append(lock_file)
                else:
                    to_keep.append(lock_file)
            rows.append((lock_file.name, pid_display, pid_alive_display, age_display, status, reason))
        except OSError:
            continue

    from rich.table import Table

    if verbose:
        table = Table(
            title="锁文件详情",
            show_lines=False,
            header_style="bold green",
            title_style="bold green",
        )
        table.add_column("锁文件")
        table.add_column("PID")
        table.add_column("活")
        table.add_column("age")
        table.add_column("状态")
        table.add_column("原因")
        for name, pid, alive, age, status, reason in rows:
            style = "red" if status == "stale" else "green"
            table.add_row(
                name,
                pid,
                alive,
                age,
                f"[{style}]{status}[/{style}]",
                reason,
            )
        ui.console.print(table)
        ui.info("")

    ui.info(f"总锁文件数: {len(lock_files)}")
    ui.info(f"[green]保留数: {len(to_keep)}[/green]")
    ui.info(f"[red]需清理: {len(to_remove)}[/red]")
    ui.info("")

    if not to_remove:
        ui.success("无需清理的孤儿锁文件")
        return

    if dry_run:
        ui.warning(f"[DRY-RUN] 将清理 {len(to_remove)} 个文件（--dry-run 未实际删除）：")
        for p in to_remove:
            ui.console.print(f"  • {p.name}")
        return

    # 实际删除：走 storage.cleanup_stale_locks 以复用其二次确认
    removed_count = storage.cleanup_stale_locks(max_age_seconds=max_age)
    ui.success(f"已清理 {removed_count} 个孤儿锁文件")

    # 校验文件确实已消失
    remaining = [p for p in to_remove if p.exists()]
    if remaining:
        ui.warning(f"仍残留 {len(remaining)} 个文件（可能被其他进程重新持有）：")
        for p in remaining:
            ui.console.print(f"  • {p.name}")


@app.command("lock-info")
def lock_info():
    """显示当前锁实现、锁目录以及锁计数诊断"""
    from rich.table import Table
    from rich.panel import Panel

    lock_dir = storage._lock_dir
    total_locks = 0
    stale_locks = 0
    live_locks = 0
    unknown_locks = 0
    now_ts = datetime.now().timestamp()

    if lock_dir.exists():
        for lock_file in lock_dir.glob("*.lock"):
            total_locks += 1
            mark = _read_pid_mark(lock_file)
            if mark is None:
                unknown_locks += 1
                continue
            pid, ts = mark
            age_s = now_ts - ts if ts <= now_ts else 0
            alive = _pid_alive(pid)
            if alive and age_s <= STALE_LOCK_MAX_AGE_SECONDS:
                live_locks += 1
            else:
                stale_locks += 1

    plat = _platform_name()
    cls_name = _lock_impl_name()

    lines = [
        f"[bold cyan]平台:[/bold cyan] {plat} ({sys.platform})",
        f"[bold cyan]锁实现:[/bold cyan] {cls_name}",
        f"[bold cyan]锁目录:[/bold cyan] {lock_dir}",
        "",
        f"[bold cyan]锁总数:[/bold cyan] {total_locks}",
        f"  [green]活跃:[/green] {live_locks}",
        f"  [red]孤儿:[/red] {stale_locks}",
        f"  [yellow]未知:[/yellow] {unknown_locks}",
        "",
        f"[dim]stale 年龄阈值: {STALE_LOCK_MAX_AGE_SECONDS}s = {STALE_LOCK_MAX_AGE_SECONDS // 3600}h[/dim]",
        f"[dim]PID 检测: os.kill(..., 0)（POSIX）/ kernel32!GetExitCodeProcess（Windows）[/dim]",
    ]

    panel = Panel("\n".join(lines), title="锁系统诊断", border_style="magenta", title_align="left")
    ui.console.print(panel)
