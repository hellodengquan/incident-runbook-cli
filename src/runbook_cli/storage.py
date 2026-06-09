from __future__ import annotations

import abc
import errno
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional

from .models import ExecutionRecord, Runbook


STALE_LOCK_MAX_AGE_SECONDS = 60 * 60 * 6
_PID_MARK_RE = None  


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            PROCESS_QUERY_INFORMATION = 0x0400
            SYNCHRONIZE = 0x00100000

            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]

            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

            handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid)
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD(0)
                ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                if not ok:
                    return False
                STILL_ACTIVE = 259
                return exit_code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
        except OSError as e:
            if e.errno == errno.ESRCH:
                return False
            if e.errno == errno.EPERM:
                return True
            return False
        else:
            return True


def _write_pid_mark(lock_path: Path, pid: Optional[int] = None) -> None:
    pid = pid or os.getpid()
    ts = datetime.now().timestamp()
    try:
        lock_path.write_text(f"PID:{pid}:{ts}\n", encoding="utf-8")
    except OSError:
        pass


def _read_pid_mark(lock_path: Path) -> Optional[tuple[int, float]]:
    try:
        if not lock_path.exists() or lock_path.stat().st_size == 0:
            return None
        raw = lock_path.read_text(encoding="utf-8", errors="ignore")
        if raw.startswith("PID:"):
            parts = raw.split(":", 3)
            if len(parts) >= 3:
                try:
                    pid = int(parts[1])
                    ts = float(parts[2].strip().splitlines()[0])
                    return (pid, ts)
                except (ValueError, IndexError):
                    return None
    except OSError:
        return None
    return None


class _PlatformLock(abc.ABC):
    """跨平台文件锁抽象基类"""

    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd: Optional[int] = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def _try_recover_stale_lock(self) -> None:
        """检测并清理孤儿锁：若记录的 PID 已死亡或锁年龄超限则删除"""
        mark = _read_pid_mark(self.lock_path)
        if mark is None:
            try:
                if self.lock_path.exists() and self.lock_path.stat().st_size == 0:
                    return
            except OSError:
                return
            now_age = None
            try:
                if self.lock_path.exists():
                    mtime = self.lock_path.stat().st_mtime
                    now_age = datetime.now().timestamp() - mtime
            except OSError:
                pass
            if now_age is not None and now_age > STALE_LOCK_MAX_AGE_SECONDS:
                try:
                    self.lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return

        pid, ts = mark
        now = datetime.now().timestamp()
        age = now - ts if ts <= now else 0
        pid_gone = not _pid_alive(pid)
        too_old = age > STALE_LOCK_MAX_AGE_SECONDS
        if pid_gone or too_old:
            try:
                if self._fd is not None:
                    try:
                        os.close(self._fd)
                    except OSError:
                        pass
                    self._fd = None
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    @abc.abstractmethod
    def acquire(self) -> None: ...

    @abc.abstractmethod
    def release(self) -> None: ...

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        self._held = False


class _FcntlLock(_PlatformLock):
    """POSIX fcntl/flock 实现（Linux / macOS / BSD）"""

    def acquire(self) -> None:
        import fcntl

        self._try_recover_stale_lock()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self._fd is None:
            self._fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        _write_pid_mark(self.lock_path)
        self._held = True

    def release(self) -> None:
        import fcntl

        if self._fd is not None and self._held:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
        self._held = False


class _MsvcrtLock(_PlatformLock):
    """Windows msvcrt.locking 实现"""

    _LOCK_FILE = 0x0002
    _UNLOCK_FILE = 0x0000

    def acquire(self) -> None:
        import msvcrt

        self._try_recover_stale_lock()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self._fd is None:
            self._fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        size = 0x7FFFFFFF
        os.lseek(self._fd, 0, os.SEEK_SET)
        msvcrt.locking(self._fd, self._LOCK_FILE, size)
        _write_pid_mark(self.lock_path)
        self._held = True

    def release(self) -> None:
        import msvcrt

        if self._fd is not None and self._held:
            try:
                size = 0x7FFFFFFF
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, self._UNLOCK_FILE, size)
            except OSError:
                pass
        self._held = False


class _NoopPlatformLock(_PlatformLock):
    """兜底：当平台 API 不可用时退化，仍通过 PID 标记做 stale 清理"""

    def acquire(self) -> None:
        self._try_recover_stale_lock()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self._fd is None:
            self._fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        _write_pid_mark(self.lock_path)
        self._held = True

    def release(self) -> None:
        self._held = False


def new_platform_lock(lock_path: Path, platform: Optional[str] = None) -> _PlatformLock:
    """根据当前平台（或覆盖参数）选择锁实现"""
    plat = (platform or sys.platform).lower()
    if plat == "win32":
        try:
            import msvcrt  # noqa: F401
            return _MsvcrtLock(lock_path)
        except ImportError:
            return _NoopPlatformLock(lock_path)
    try:
        import fcntl  # noqa: F401
        return _FcntlLock(lock_path)
    except ImportError:
        return _NoopPlatformLock(lock_path)


_LOCK_SUBCLASS_BY_PLATFORM = {
    "posix": _FcntlLock,
    "linux": _FcntlLock,
    "linux2": _FcntlLock,
    "darwin": _FcntlLock,
    "macos": _FcntlLock,
    "freebsd": _FcntlLock,
    "openbsd": _FcntlLock,
    "netbsd": _FcntlLock,
    "win32": _MsvcrtLock,
    "windows": _MsvcrtLock,
}


def lock_implementation_class(platform: str) -> type[_PlatformLock]:
    """给测试/诊断用：直接返回平台对应的锁类"""
    plat = platform.lower()
    if plat in ("win32", "windows"):
        return _MsvcrtLock
    if plat in ("noop", "none", "null"):
        return _NoopPlatformLock
    return _FcntlLock


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

    def cleanup_stale_locks(self, max_age_seconds: Optional[int] = None) -> int:
        """扫描整个 .locks 目录并删除孤儿锁文件；返回清理掉的数量"""
        removed = 0
        global STALE_LOCK_MAX_AGE_SECONDS
        limit = max_age_seconds if max_age_seconds is not None else STALE_LOCK_MAX_AGE_SECONDS
        if not self._lock_dir.exists():
            return 0
        now_ts = datetime.now().timestamp()
        for lock_file in sorted(self._lock_dir.glob("*.lock")):
            try:
                mark = _read_pid_mark(lock_file)
                delete = False
                if mark is None:
                    try:
                        st = lock_file.stat()
                        if (now_ts - st.st_mtime) > limit and st.st_size == 0:
                            delete = True
                    except OSError:
                        continue
                else:
                    pid, ts = mark
                    age = now_ts - ts if ts <= now_ts else 0
                    if not _pid_alive(pid) or age > limit:
                        delete = True
                if delete:
                    # 快速竞争检测：不要和正持有锁的进程冲突
                    if mark is None:
                        lock_file.unlink(missing_ok=True)
                        removed += 1
                    else:
                        # 再次确认 PID 仍然死
                        pid, _ = mark
                        if not _pid_alive(pid):
                            lock_file.unlink(missing_ok=True)
                            removed += 1
            except OSError:
                continue
        return removed

    def _acquire_lock(self, lock_path: Path) -> _PlatformLock:
        lock = new_platform_lock(lock_path)
        lock.acquire()
        return lock

    def _release_lock(self, lock: _PlatformLock) -> None:
        try:
            lock.release()
        finally:
            lock.close()

    def _atomic_write(self, target: Path, content: str, kind: str, record_id: str) -> None:
        lock_path = self._lock_path(kind, record_id)
        lock = self._acquire_lock(lock_path)
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
            self._release_lock(lock)

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
        lock = self._acquire_lock(lock_path)
        try:
            path = self._runbook_path(runbook_id)
            if path.exists():
                path.unlink()
                return True
            return False
        finally:
            self._release_lock(lock)

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
