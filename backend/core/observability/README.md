# 可观测性 Viewer 使用指南

通用 Agent 性能数据统计脚本，支持不同 agent 类型的指标分析。解析 `LocalMetricsCollector` 生成的 `metrics_logs.jsonl`，输出 Agent 执行、LLM 调用、工具使用、沙箱操作等统计与性能分析。

## 功能特性

- **多 agent 预设**：AgentPress、Generic 等预设，可自定义 JSON 配置
- **可配置日志路径**：`--log-dir` / `--file` / 配置 / 环境变量
- **自动日志发现**：在 `log_dir` 下自动选取最新 `metrics_logs_*.jsonl`
- **多维度分析**：Agent、LLM、Tool、Sandbox、Context、Memory
- **端到端性能**：会话时长、组件耗时、并行重叠分析
- **Trace 过滤**：按 trace_id 筛选

## 使用方法

### 基本用法

```bash
cd suna/backend
python -m core.observability.viewer
```

不指定参数时，使用默认 `logs/` 目录下最新日志，并采用 `agentpress` 预设。

### 命令行参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `--file` | `-f` | 指定日志文件路径 |
| `--log-dir` | `-d` | 指定日志目录（自动选最新文件） |
| `--trace-id` | `-t` | 只分析指定 trace |
| `--agent-type` | `-a` | 预设：`agentpress`、`generic`，默认 `agentpress` |
| `--config` | `-c` | 使用自定义 JSON 配置（覆盖 preset） |

### 日志路径解析顺序

1. `--file` 直接指定文件
2. `--log-dir` / 配置中的 `log_dir`
3. 环境变量 `METRICS_LOG_DIR`
4. 默认：`{cwd}/logs`

### 示例

```bash
# 使用 Suna 配置
python -m core.observability.viewer --config core/observability/viewer_config.suna.json

# 通用模式（任意 agent，不排除工具）
python -m core.observability.viewer --agent-type generic

# 指定日志目录
python -m core.observability.viewer --log-dir /var/log/agent

# 环境变量指定
METRICS_LOG_DIR=backend/logs python -m core.observability.viewer

# 指定文件 + 指定 trace
python -m core.observability.viewer -f logs/metrics_logs_20231027_103000.jsonl -t <trace_id>
```

## 预设说明

| 预设 | 说明 |
|------|------|
| `agentpress` | 排除任务/内存工具，启用 context、memory 专项分析 |
| `generic` | 不排除任何工具，不启用 context/memory 专项，适用于任意 agent |

## 配置文件

复制 `viewer_config.example.json` 并修改，或参考 `viewer_config.suna.json`：

```json
{
  "log_dir": "logs",
  "excluded_tools": ["create_tasks", "update_tasks", ...],
  "context_tools": ["create_tasks", "update_tasks", ...],
  "memory_tools": ["manage_core_memory"],
  "event_types": { ... },
  "field_mapping": { ... }
}
```

- `log_dir`：日志目录，相对 cwd 或绝对路径
- `excluded_tools`：从通用工具统计中排除
- `context_tools`：`null` 则不启用 context 专项分析
- `memory_tools`：`null` 则不启用 memory 专项分析
- `event_types` / `field_mapping`：用于适配不同日志格式

## 输出示例

```
Found 1 traces:
Trace ID                                 Events     Start Time                     Duration (s)
----------------------------------------------------------------------------------------------------
a1b2c3d4-e5f6-...                        50         2023-10-27T10:30:00+00:00      12.50

####################################################################################################
TRACE: a1b2c3d4-e5f6-...
####################################################################################################

--- End-to-End Performance Statistics ---
Total Session Duration: 12.50 s
...

--- LLM Statistics ---
Model Name                               Count      Total Dur (ms)  Avg Dur (ms)    Avg Tokens      Errors
...
```

## 依赖

- 日志由 `LocalMetricsCollector` 写入，格式为 JSONL
- 事件类型：`tool_execution`、`llm_call`、`agent_execution`、`agent_sandbox` 等
