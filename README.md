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
    ├── storage.py              # JSON 文件存储层
    ├── ui.py                   # Rich UI 组件（表格/颜色/进度条）
    └── commands/
        ├── __init__.py
        ├── runbook_cmds.py     # 预案管理命令
        ├── exec_cmds.py        # 执行追踪命令
        └── history_cmds.py     # 历史回顾命令
```

## 许可证

MIT License
