# 运维操作手册（Operations Guide）

> 文档版本：1.0 | 适用版本：runbook-cli v1.x

本手册补充 `README.md`，详细说明**并发写入风险**、**导出文件命名规范**，以及 SRE/运维团队**典型值班场景操作流程**。

---

## 1. 数据存储与并发写入风险

### 1.1 存储架构
Runbook CLI 采用**本地 JSON 文件存储**，所有数据保存在用户的 `~/.runbook-cli/` 目录下：

```
~/.runbook-cli/
├── runbooks/               # 每个预案一个 JSON 文件（<id>.json）
│   ├── <runbook-id>.json   # 写入时机：create/edit/add-step/delete 等
│   └── ...
└── executions/             # 每次执行一个 JSON 文件
    ├── <execution-id>.json # 写入时机：step/start/pause/resume/finish 等
    └── ...
```

### 1.2 并发写入风险说明

**⚠️ 重要：Runbook CLI 未内置文件锁，多人共享同一份存储会出现以下风险：**

| 风险场景 | 后果 | 推荐规避方式 |
|----------|------|-------------|
| 两人同时编辑同一个预案（`runbook edit`） | 后写入的内容覆盖前者，造成数据丢失 | 1. 同一时刻只允许一人编辑 2. 编辑前先 `runbook show` 确认状态 |
| 两人同时推进同一次执行（`exec step`） | 步骤状态互相覆盖，时间线错乱 | **原则：一次执行会话只能由一位值班人主导操作**，交接时显式说明 |
| 两人并发 `runbook create` | 不会冲突（ID 随机），但可能产生同名预案 | 创建前先 `runbook list` 查找是否已存在同名预案 |
| 同机多终端 `history export` | 不会冲突（只读） | - |

### 1.3 多人值班协作建议

1. **独立存储目录**：每位值班人使用独立的 `~/.runbook-cli` 目录（默认行为），不要通过共享目录/NAS 共享存储。
2. **预案集中维护 + 本地导入**：预案定义（Runbook）由团队共同维护在 Git 仓库，值班前通过脚本同步到本地。
3. **执行会话单一操作人**：每次执行 `exec start` 的值班人即为唯一操作者，交接时通过 `history export` 导出报告作为交接材料，新值班人启动新的 `exec start`。
4. **定期归档**：每日值班结束时，将当日的 `executions/*.json` 导出 Markdown 报告，提交到知识库或工单系统。

### 1.4 数据备份建议

```bash
# 手动备份（建议每日一次）
tar -czf runbook-backup-$(date +%Y%m%d).tar.gz ~/.runbook-cli/

# 仅备份执行记录（体积小，可高频备份）
cp -r ~/.runbook-cli/executions/ /mnt/backup/runbook-exec-$(date +%Y%m%d)/
```

---

## 2. 导出文件命名规范

### 2.1 默认命名规则

`history export` 命令在未指定 `-o` 时会自动生成文件名，规则如下：

```
runbook-<预案名称>-<开始时间戳>.<后缀>
```

其中：
- **预案名称**：直接取自执行记录的 `runbook_name` 字段
- **开始时间戳**：`YYYYMMDD-HHMMSS` 格式，取自 `started_at`；若 `started_at` 为空则使用当前时间
- **后缀**：根据 `--format` 决定，`json` → `.json`，`md/markdown` → `.md`，`txt` → `.txt`

**示例**：

| 执行记录字段 | 自动生成的文件名 |
|-------------|-----------------|
| runbook_name="MySQL 主库故障切换"，started_at=2026-06-10 09:15:30，format=md | `runbook-MySQL 主库故障切换-20260610-091530.md` |
| runbook_name="线上服务OOM处理"，started_at 为空，format=json | `runbook-线上服务OOM处理-20260610-100000.json` |

### 2.2 团队规范命名（推荐）

实际值班中建议**始终显式指定 `-o`**，使用以下命名格式：

```
INC-<事件ID>-<预案缩写>-<YYYYMMDD>-v<版本>.<后缀>
```

**字段说明**：

| 字段 | 说明 | 示例 |
|------|------|------|
| `INC-<事件ID>` | 事件/工单系统中的唯一编号 | `INC-20260610-003` |
| `<预案缩写>` | 预案名称的英文字母缩写，4-12 字符 | `mysql-failover`（MySQL主库切换）、`k8s-node`（K8s节点异常） |
| `<YYYYMMDD>` | 日期 | `20260610` |
| `v<版本>` | 同一事件多次导出区分版本，`v1`/`v2`/`v-final` | `v-final` |
| `<后缀>` | `.md` 或 `.json` | `.md` |

**推荐命令**：

```bash
# 示例：事件 INC-20260610-003 执行 MySQL 主库切换的最终报告
runbook history export <执行ID> \
    --format md \
    -o ./reports/INC-20260610-003-mysql-failover-20260610-v-final.md

# 示例：过程性中间报告（JSON 归档）
runbook history export <执行ID> \
    --format json \
    -o ./reports/INC-20260610-003-mysql-failover-20260610-v1.json
```

**为什么推荐这种命名？**
- 可以直接与事件/工单系统 ID 关联，便于追溯
- 前缀按字母/数字排序时，同一事件的报告自然归拢在一起
- 缩写避免中文文件名在跨系统（Windows/Linux/macOS）传输时出现编码问题

### 2.3 导出内容概览

| 格式 | 适用场景 | 主要内容 |
|------|---------|---------|
| **Markdown (.md)** | 邮件/文档归档、复盘会议 | 结构化报告，含基本信息、步骤时间线、操作备注、处理总结 |
| **JSON (.json)** | 二次处理、自动化分析 | 完整原始数据，便于程序化解析 |
| **TXT (.txt)** | 终端分享、即时通讯粘贴 | 纯文本无渲染，便于快速复制 |

---

## 3. 典型值班场景操作流程

### 场景 A：接到告警 → 启动预案 → 推进执行 → 收尾导出

**参与角色**：单人值班（SRE oncall）

**时间线**：

```
 T+0min  接收到 Zabbix/Prometheus 告警，判断为"MySQL 主库不可达"
 T+1min  查询预案并启动执行
 T+3min  逐步推进，每步记录备注
 T+25min 主从切换完成，业务接口恢复
 T+30min 结束执行，填写总结，导出报告
 T+32min 在值班交接群内粘贴报告链接
```

**详细操作步骤**：

```bash
# 第 1 步：确认并启动执行
runbook runbook list --severity critical        # 找对应级别的预案
runbook runbook show "MySQL 主库故障切换"          # 快速浏览步骤确认无误

runbook exec start "MySQL 主库故障切换" \
    --operator "$(whoami)" \
    --incident-id "INC-20260610-003"

# 第 2 步：逐步推进（边操作边记录备注）
# 步骤 1
runbook exec step 1                             # 快捷开始步骤 1
#  ... 实际操作中 ...
runbook exec step complete --notes "主库 10.0.0.100:3306 完全无法连接，IPMI 显示硬件告警"

# 步骤 2
runbook exec step 2 --notes "电话通知 DBA 李工（138xxxx）"
runbook exec step complete --notes "微信群已公告，业务方确认知晓"

# 步骤 3-5（同上）
runbook exec step 3
# ... 人工操作 ...
runbook exec step complete --notes "选中 slave-01，Seconds_Behind_Master=0"

runbook exec step 4
runbook exec step complete --notes "STOP SLAVE / RESET MASTER 已执行，应用 DNS 已切换"

runbook exec step 5
runbook exec step complete --notes "核心接口全部 200 OK，TPS 恢复正常水平"

# 第 3 步：跳过非关键步骤，结束执行
runbook exec step skip 6 --notes "复盘留待明日班会进行"

runbook exec finish --summary "
【故障根因】主库服务器磁盘背板故障，导致 MySQL 进程崩溃
【处理过程】按照预案流程完成主从切换，提升 slave-01 为新主库
【影响范围】订单写入中断约 18 分钟
【后续跟进】1. 服务器返修；2. 评估磁盘监控告警阈值；3. 明日复盘会议
"

# 第 4 步：导出并归档
runbook history export <执行ID> \
    --format md \
    -o ./reports/INC-20260610-003-mysql-failover-20260610-v-final.md

# JSON 备份一份（便于后续自动化统计）
runbook history export <执行ID> \
    --format json \
    -o ./reports/INC-20260610-003-mysql-failover-20260610-v-final.json
```

---

### 场景 B：多轮班交接（白班 → 夜班）

**参与角色**：白班值班人 A、夜班值班人 B

**交接标准流程**：

```
【值班人 A（白班，20:00 下班前）】

# 1. 若仍有进行中的执行，先暂停（明确暂停原因）
runbook exec pause --reason "白班结束，交接给夜班值班人 B（王五），
已确认目前新主库运行正常，剩余步骤：完善监控和复盘"

# 2. 导出 Markdown 报告（即使未完成也要导出）
runbook history export <执行ID> --format md \
    -o ./reports/INC-20260610-003-mysql-failover-20260610-v-handover.md

# 3. 查看当日统计（作为值班日报基础）
runbook history summary --last-days 1
runbook dashboard

# 4. 发送交接信息到值班群
# 模板：
# 【值班交接】白班 → 夜班
#  • 进行中事件：INC-20260610-003 MySQL 主库切换
#  • 当前状态：已暂停，步骤 5/6，业务已恢复
#  • 交接报告：<file link>
#  • 待办：(1) 完善新主库监控告警；(2) 明日复盘
```

```
【值班人 B（夜班，接手时）】

# 1. 恢复执行
runbook exec resume

# 2. 查看当前进度
runbook exec current

# 3. 继续推进剩余步骤
runbook exec step 6
# ... 处理 ...
runbook exec step complete --notes "夜班补充：已配置新主库的磁盘、CPU 告警规则"

# 4. 结束执行（如全部完成）
runbook exec finish --summary "夜班补充：监控已补齐，业务稳定运行 4 小时无异常"

# 5. 导出最终版
runbook history export <执行ID> --format md \
    -o ./reports/INC-20260610-003-mysql-failover-20260610-v-final.md
```

---

### 场景 C：预案维护（非值班时间）

**参与角色**：全体 SRE，按季度迭代

```
# 1. 从主分支拉取最新预案（假设存放在 Git 仓库 /ops/runbooks/）
#    说明：团队应将 runbooks/*.json 纳入 Git 管理
cp /ops/runbooks/*.json ~/.runbook-cli/runbooks/

# 2. 季度演练：使用 init-demo 构造假数据演练
runbook init-demo

# 3. 新增预案（由主值班人发起，交互模式）
runbook runbook create --interactive
# 提示：预案编写完成后，先 activate 之前至少做一次 dry-run（模拟执行）

# 4. 模拟演练（在不记录到真实 executions 的情况下可直接使用临时目录）
mkdir -p /tmp/runbook-drill
export HOME=/tmp/runbook-drill
runbook init-demo
runbook exec start "MySQL 主库故障切换" --operator "演练"
runbook exec step 1
# ... 完整过一遍 ...
# 演练结束，清理
rm -rf /tmp/runbook-drill

# 5. 将新/修改后的预案同步回 Git
cp ~/.runbook-cli/runbooks/*.json /ops/runbooks/
cd /ops/runbooks && git add -A && git commit -m "runbook: 更新MySQL切换预案新增监控步骤"
```

---

## 4. 常见问题（FAQ）

### Q1：`exec step` 误操作了，能回退吗？
**目前不支持步骤回退**。建议的应急处理：
- 误标记为 `complete` → 无需回退，后续步骤正常推进，在 `finish --summary` 中说明
- 误标记为 `fail` → 立即使用 `exec abort --reason "误操作，重新开始"` 并启动新的 `exec start`
- 误 `skip` → 在后续步骤中补充操作记录，或在 summary 中说明实际已执行

> 注：JSON 文件是纯文本，紧急时可直接编辑对应的 `~/.runbook-cli/executions/<id>.json`，修改后重新保存即可（不推荐常规操作）。

### Q2：如何一次性删除所有执行记录（演练后清理）？
```bash
# 仅清理执行记录（保留预案）
rm -f ~/.runbook-cli/executions/*.json

# 完全重置（慎用）
rm -rf ~/.runbook-cli/
```

### Q3：统计中成功率异常偏高/偏低？
- 若大量使用 `exec finish --force`，未完成步骤会被记为 `skipped`，不算失败 → 成功率偏高
- 若中途使用 `exec abort`，所有未完成步骤记为 `failed` → 成功率偏低
- 建议：尽量让每个步骤走到正常状态（`complete` / `skip` 或 `fail`），减少强制终止

### Q4：多人值班时存储如何统一？
建议 3 种方案，按团队规模选择：

| 方案 | 适用规模 | 实施方式 |
|------|---------|---------|
| 本地独立 + Git 同步 | ≤5 人 | 各人本地独立存储，runbooks 目录入 Git，每日提交 |
| 共享 NAS + 目录锁 | 6-20 人 | `~/.runbook-cli` 指向 NAS，使用 `flock` 脚本包装 CLI 入口 |
| 迁移为 Server-Client 架构 | >20 人 | 将 storage 层替换为 REST API，后端接入 MySQL/PostgreSQL |

---

## 5. 附录：命令速查索引

- 预案管理（11 个命令）：`create / list / show / delete / edit / add-step / remove-step / activate / archive / copy`
- 执行追踪（12 个命令）：`start / step (start|complete|skip|fail|note) / status / current / pause / resume / finish / abort`
- 历史回顾（4 个命令）：`list / show / summary / export`
- 全局工具（2 个命令）：`dashboard / init-demo`

完整命令细节请参考 `README.md` 中的「命令速查」表格。
