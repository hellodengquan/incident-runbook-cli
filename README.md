# 应急 Runbook CLI 工具

基于 Python + Typer + Rich 开发的值班应急响应工具，用于管理应急预案（Runbook）、追踪执行步骤状态、回顾处理记录。专为 SRE/运维值班场景优化，支持交互式操作、彩色输出、进度可视化等体验。

## 功能特性

### 1. 预案清单管理 (`runbook runbook`)
- **创建预案**：支持交互模式，可定义多步骤和检查项
- **编辑预案**：修改基本信息、标签、增删步骤
- **状态管理**：草稿 → 激活 → 归档 全生命周期
- **过滤查询**：按状态、严重级别、标签筛选
- **复制克隆**：基于已有预案快速创建新预案

### 2. 执行步骤追踪 (`runbook exec`)
- **开始执行**：创建执行会话，关联事件 ID 和值班人
- **步骤推进**：start → complete / skip / fail 五步状态流转
- **快捷操作**：`exec step 1` 直接开始步骤 1，无需额外参数
- **暂停/恢复**：支持暂停执行并记录原因
- **强制结束**：提前终止执行，自动处理未完成步骤
- **实时状态**：进度条 + 彩色表格展示执行进展

### 3. 处理记录回顾 (`runbook history`)
- **历史列表**：多维度过滤（预案、状态、值班人、时间范围）
- **详情查看**：步骤级完整时间线、操作备注
- **统计摘要**：成功率、平均耗时、分预案统计
- **多格式导出**：JSON、Markdown、纯文本三种格式

### 4. 交互体验优化
- **彩色状态标识**：不同状态使用不同颜色（绿=完成、黄=进行中、红=失败等）
- **交互式确认**：危险操作前二次确认
- **进度条可视化**：整体进度实时展示
- **仪表板总览**：`dashboard` 命令一键查看全局状态
- **示例数据**：`init-demo` 快速初始化演示预案

## 安装

```bash
# 克隆项目后进入目录
cd incident-runbook-cli

# 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 或使用 uv（推荐）
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

## 快速开始

```bash
# 1. 初始化示例数据（可选）
python runbook.py init-demo

# 2. 查看所有预案
python runbook.py runbook list

# 3. 查看仪表板
python runbook.py dashboard

# 4. 开始执行一个预案
python runbook.py exec start "MySQL 主库故障切换" --operator "张三" --incident-id "INC-001"

# 5. 逐步推进执行（快捷方式）
python runbook.py exec step 1                     # 开始步骤 1
python runbook.py exec step complete --notes "..." # 完成当前步骤
python runbook.py exec step 2                     # 开始步骤 2
python runbook.py exec step skip 3                # 跳过步骤 3

# 6. 查看当前执行状态
python runbook.py exec status
# 或快捷方式
python runbook.py exec current

# 7. 全部处理完成后结束执行
python runbook.py exec finish --summary "..."

# 8. 查看历史记录和统计
python runbook.py history list
python runbook.py history summary --last-days 7

# 9. 导出处理报告
python runbook.py history export <执行ID> --format md -o report.md
```

## 命令速查

### 预案管理

| 命令 | 说明 |
|------|------|
| `runbook runbook create` | 创建新预案（交互模式） |
| `runbook runbook list` | 列出预案（支持过滤） |
| `runbook runbook show <ID/名称>` | 查看预案详情 |
| `runbook runbook edit <ID/名称>` | 编辑预案信息 |
| `runbook runbook add-step <ID/名称>` | 添加执行步骤 |
| `runbook runbook remove-step <ID/名称> <步骤号>` | 移除执行步骤 |
| `runbook runbook activate <ID/名称>` | 激活预案 |
| `runbook runbook archive <ID/名称>` | 归档预案 |
| `runbook runbook copy <源ID> --name <新名称>` | 克隆预案 |
| `runbook runbook delete <ID/名称>` | 删除预案 |

### 执行追踪

| 命令 | 说明 |
|------|------|
| `runbook exec start <预案ID/名称>` | 开始执行（创建会话） |
| `runbook exec step <N>` | 快捷：开始第 N 步 |
| `runbook exec step start <步骤号>` | 开始指定步骤 |
| `runbook exec step complete` | 完成当前步骤 |
| `runbook exec step skip <步骤号>` | 跳过步骤 |
| `runbook exec step fail <步骤号>` | 标记步骤失败 |
| `runbook exec step note <步骤号> --notes "..."` | 添加步骤备注 |
| `runbook exec status / current` | 查看当前执行状态 |
| `runbook exec pause --reason "..."` | 暂停执行 |
| `runbook exec resume` | 恢复执行 |
| `runbook exec finish --summary "..."` | 结束执行（正常） |
| `runbook exec abort --reason "..."` | 中止执行（异常） |

### 历史回顾

| 命令 | 说明 |
|------|------|
| `runbook history list` | 列出执行历史（支持多维过滤） |
| `runbook history show <执行ID>` | 查看某次执行完整详情 |
| `runbook history summary --last-days 7` | 统计摘要 |
| `runbook history export <ID> --format json\|md\|txt` | 导出报告 |

### 其他

| 命令 | 说明 |
|------|------|
| `runbook dashboard` | 全局仪表板 |
| `runbook init-demo` | 初始化示例数据 |
| `runbook --version` | 显示版本信息 |

## 数据存储

所有数据存储在 `~/.runbook-cli/` 目录下：

```
~/.runbook-cli/
├── runbooks/          # 预案定义（每个预案一个 JSON）
│   ├── <runbook-id>.json
│   └── ...
└── executions/        # 执行记录（每次执行一个 JSON）
    ├── <execution-id>.json
    └── ...
```

## 典型值班场景示例

### 场景一：数据库主库故障切换

```bash
# 接收到告警，先启动执行
$ runbook exec start "MySQL 主库故障切换" --operator "李工" -i "INC-20260610-001"

# 步骤1：确认故障
$ runbook exec step 1 --notes "Zabbix告警，10.0.0.100 3306不通"
# 人工排查后确认
$ runbook exec step complete --notes "主库硬件故障，确认需要切换"

# 步骤2：通知
$ runbook exec step 2 --notes "电话通知了DBA负责人"
$ runbook exec step complete --notes "微信群已公告，业务方已知晓"

# 步骤3-5：选择新主、切换、验证
$ runbook exec step 3 -n "选定 slave-01，延迟最小"
$ runbook exec step complete
$ runbook exec step 4 ...
$ runbook exec step 5 ...

# 步骤6：复盘（时间不够先跳过）
$ runbook exec step skip 6 --notes "明天上班再补复盘"

# 结束
$ runbook exec finish --summary "主库硬件故障，已完成主从切换，业务恢复正常，耗时约30分钟"

# 导出报告归档
$ runbook history export <执行ID> -f md -o reports/INC-20260610-001.md
```

### 场景二：快速创建新预案

```bash
# 交互模式创建（推荐）
$ runbook runbook create --interactive
# 依次输入：预案名称、描述、严重级别，然后逐个定义步骤

# 非交互模式（脚本化）
$ runbook runbook create -n "Redis 集群脑裂处理" \
    -d "当 Redis Cluster 发生脑裂时的处理流程" \
    -s high \
    -t Redis -t 缓存 --no-interactive

# 添加步骤
$ runbook runbook add-step "Redis 集群脑裂处理" -t "确认脑裂状态" -d "检查 cluster info"
$ runbook runbook add-step "Redis 集群脑裂处理" -t "隔离错误分片"
$ runbook runbook add-step "Redis 集群脑裂处理" -t "重建集群"

# 激活后即可使用
$ runbook runbook activate "Redis 集群脑裂处理"
```

## 技术栈

- **Python 3.9+**
- **Typer** — CLI 框架，基于类型注解自动生成帮助
- **Rich** — 终端彩色输出、表格、进度条、交互式提示
- **Pydantic** — 数据模型校验与序列化
- **python-dateutil** — 日期处理

## 项目结构

```
incident-runbook-cli/
├── requirements.txt
├── pyproject.toml
├── runbook.py                  # 入口脚本
└── src/runbook_cli/
    ├── __init__.py
    ├── main.py                 # Typer 主入口，集成所有子命令
    ├── models.py               # Pydantic 数据模型
    ├── storage.py              # JSON 文件存储层（含跨平台锁）
    ├── ui.py                   # Rich UI 组件（表格/颜色/进度条）
    └── commands/
        ├── __init__.py
        ├── runbook_cmds.py     # 预案管理命令
        ├── exec_cmds.py        # 执行追踪命令
        ├── history_cmds.py     # 历史回顾命令
        └── admin_cmds.py       # 运维管理（锁清理/诊断）
```

## 并发与锁

多人值班时，多人/多 shell 同时操作同一数据目录会导致 JSON 半写损坏。runbook-cli 在 `storage.py` 内实现了**跨平台文件锁** + **原子替换**双保险，并辅以**孤儿锁自动清理**。

### 1. 三种锁实现（按平台自动选择）

| 实现类 | 平台 | 底层 API | 说明 |
|--------|------|----------|------|
| `_FcntlLock` | POSIX（Linux / macOS / BSD） | `fcntl.flock(fd, LOCK_EX)` | 内核级建议锁，`LOCK_EX` 跨进程独占；持锁进程崩溃由内核自动释放 |
| `_MsvcrtLock` | Windows | `msvcrt.locking(fd, _LK_LOCK, 0x7FFFFFFF)` | MSVC 运行时锁定，锁定从文件头起 `2GB` 范围 |
| `_NoopPlatformLock` | 兜底（两者都不可用） | 无系统调用 | 不提供真实互斥，仍保留 PID 标记 + stale 清理，靠 `os.replace()` 原子性兜底 |

> **选择逻辑**：`new_platform_lock()` 读取 `sys.platform`，`win32` 尝试 `import msvcrt`，否则 fallback 到 `_FcntlLock`（需 `import fcntl`），再退化到 `_NoopPlatformLock`。

### 2. 双保险写入流程

每次 `save_runbook` / `save_execution` 都会执行：

```
① 获取记录级排他锁（fcntl / msvcrt）
   │
   ├─ 获取前运行 stale 检测（见 §3）
   │
② 写临时文件：<target>.NNNNNN.tmp（NamedTemporaryFile，与目标同目录 → 保证同一 FS）
   │
③ os.replace(tmp, target)  —— 原子 rename 系统调用
   │
④ 释放锁并关闭 fd
```

即使并发中锁完全失效（Noop 模式或 Windows 9x），`os.replace()` 仍保证目标文件要么是完整的旧版本，要么是完整的新版本，**绝不会出现半截 JSON**。

### 3. 孤儿锁（Stale Lock）检测与清理

锁文件除了被系统持有锁外，还会写入文本标记：`PID:<持有者PID>:<unix_ts时间戳>\n`

**清理触发点**：
- **写路径自动**：每次 `lock.acquire()` 前执行 `_try_recover_stale_lock()`，若锁已陈旧则 unlink 重建
- **运维命令**：`runbook admin clean-locks` 可定期或事故后批量扫描

**陈旧判定条件（满足任一即判为孤儿）**：

| 条件 | 说明 |
|------|------|
| 标记的 PID 不存在（`_pid_alive(pid)` 为 False） | 持锁进程已崩溃/被杀 |
| 锁年龄 `> STALE_LOCK_MAX_AGE_SECONDS = 21600 秒（6 小时）` | 时间戳太老即使 PID 被重用也安全清理 |
| 空文件 + mtime 超阈值 | 早期版本遗留的无标记锁文件 |

**PID 存活检测原理**：

| 平台 | 实现 |
|------|------|
| POSIX | `os.kill(pid, 0)` —— 空信号：返回成功则进程存在，`ESRCH` 说明不存在，`EPERM` 说明存在但无权限（视为存活） |
| Windows | `kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE)` → `GetExitCodeProcess` → 若等于 `STILL_ACTIVE(259)` 判为存活，否则已退出；`CloseHandle` 收尾 |

### 4. 6 小时阈值的依据

`STALE_LOCK_MAX_AGE_SECONDS = 60 * 60 * 6 = 21600s`：

1. **值班周期覆盖**：一线 SRE 常见值班为 8h 白班 / 12h 夜班 / 24h oncall，取 6h 恰好是一次标准故障处置（含事后复盘）的**上限 2～3 倍**，真锁不应被误判为孤儿；
2. **PID 复用安全**：Linux 默认 `pid_max=32768`，繁忙主机一天内 PID 可能复用 2 次以上，6 小时窗口极大概率**不会**把重用的 PID 当成原持有者；
3. **锁堆积容忍**：每人每命令一个锁文件（大小 20～40 字节），6 小时累积量即使极端情况也只有几百个，占磁盘可忽略；
4. **可调整**：`clean-locks` 的 `--max-age N` 可按实际运维节奏动态覆盖（例如一周清理改成 `--max-age 604800`）。

### 5. 运维操作方法

#### (1) 诊断锁系统状态

```bash
runbook admin lock-info
```

输出：当前平台、锁实现类、锁目录路径、活跃 / 孤儿 / 未知 锁数量、6 小时阈值、PID 检测方式。

#### (2) 预演清理（DRY-RUN，推荐先跑）

```bash
# 只列出将被清理的孤儿锁，不删文件
runbook admin clean-locks --dry-run -v
# 自定义阈值 30 分钟：更激进地清理
runbook admin clean-locks --dry-run --max-age 1800
```

`-v` 模式下会打印 Rich 表格：锁文件名、持有者 PID、PID 是否活、锁龄、keep/stale 状态、判定原因。

#### (3) 实际清理

```bash
# 常规清理（阈值 = 6h）
runbook admin clean-locks

# 故障后立即清理（阈值 = 1 分钟）
runbook admin clean-locks --max-age 60 -v
```

返回结果会列出**实际删除数量**，并对「本应删除但仍残留」的文件给出 yellow warning（通常是被其他进程重新持有，属正常情况）。

#### (4) 建议巡检 cron

```cron
# 每天 04:00 值班交接前后清理一遍，-v 结果投递到日志
0 4 * * * /usr/local/bin/runbook admin clean-locks --max-age 7200 -v >> /var/log/runbook-clean-locks.log 2>&1
```

## 许可证

MIT License
