# 压测脚本接口规范

本文档描述压测流程中**基本无需调整**的组件的输入/输出接口。只要按此规范生产或消费数据，即可与 `analyze.py`、`monitor.py` 及 Locust 框架无缝对接。

---

## 1. Locust 输出：Stats History CSV

**来源**：Locust 执行 `--csv=prefix` 时自动生成 `{prefix}_stats_history.csv`

**用途**：`analyze.py` 读取后生成延迟、吞吐量图表

| 列名 | 类型 | 说明 |
|------|------|------|
| `Timestamp` | float | Unix 时间戳（秒） |
| `Total Median Response Time` | float | 总请求 P50 延迟（毫秒） |
| `Total 95%` | float | 总请求 P95 延迟（毫秒） |
| `Requests/s` | float | 每秒请求数（RPS） |

**说明**：以上为 `analyze.py` 实际使用的列。Locust 默认导出格式包含这些列；若使用自定义 Locust 脚本，需确保 `events.request.fire` 或等价方式产生的统计数据写入上述列名。

**文件名约定**：`*_stats_history.csv`，便于 `analyze.py` 自动扫描

---

## 2. 资源监控输出：Resource Stats CSV

**来源**：`monitor.py` 运行后生成 `resource_stats_{node_name}.csv`

**用途**：`analyze.py` 读取后生成 CPU、内存、网络、磁盘 I/O 图表

### 2.1 列定义

| 列名 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `timestamp` | str | ISO 8601 | 采样时间 |
| `container_name` | str | - | Docker 容器名称 |
| `cpu_percent` | float | % | CPU 使用率 |
| `mem_percent` | float | % | 内存使用率（相对 limit） |
| `mem_usage_mb` | float | MB | 内存用量（绝对） |
| `net_rx_mb` | float | MB | 网络接收累计量 |
| `net_tx_mb` | float | MB | 网络发送累计量 |
| `disk_read_mb` | float | MB | 磁盘读累计量 |
| `disk_write_mb` | float | MB | 磁盘写累计量 |

**说明**：`net_*`、`disk_*` 为累计值，`analyze.py` 内部会做差分并转换为速率（MB/s）。

### 2.2 文件 naming 约定

- 格式：`resource_stats_{node_name}.csv`
- 示例：`resource_stats_node_a.csv`、`resource_stats_node_b.csv`
- `analyze.py` 会按 `resource_stats_*.csv` 模式查找

---

## 3. monitor.py 命令行接口

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--node-name` | 是 | - | 节点标识，用于输出文件名 |
| `--interval` | 否 | 5 | 采样间隔（秒） |
| `--duration` | 否 | 300 | 运行时长（秒） |
| `--patterns` | 是 | - | 容器名匹配的正则，可多个 |
| `--output-dir` | 否 | 当前目录 | 输出目录 |

**示例**：
```bash
python monitor.py --node-name node_a --interval 5 --duration 600 \
  --patterns "supabase" "suna" --output-dir ./monitor_data
```

---

## 4. analyze.py 输入/输出

### 4.1 输入

| 输入 | 格式 | 说明 |
|------|------|------|
| Locust 数据 | `*_stats_history.csv` | 压测时延与 RPS |
| 资源数据 | `resource_stats_*.csv` | 容器 CPU/内存/网络/磁盘 |

可通过以下方式指定：
- 位置参数：`results_dir`，脚本会在该目录下自动查找上述文件
- `--locust-file`：指定 Locust CSV 路径
- `--resource-files`：指定多个资源 CSV 路径

### 4.2 输出

| 文件 | 数据来源 | 说明 |
|------|----------|------|
| `latency_p50_p95.png` | Locust | P50/P95 延迟趋势 |
| `throughput_rps.png` | Locust | RPS 吞吐量 |
| `cpu_usage_{prefix}.png` | 资源 | 按容器分组 CPU 使用率 |
| `memory_usage_{prefix}.png` | 资源 | 按容器分组内存使用量 |
| `network_io_{prefix}.png` | 资源 | 按容器分组网络 I/O 速率 |
| `disk_io_{prefix}.png` | 资源 | 按容器分组磁盘 I/O 速率 |

**说明**：`{prefix}` 为 `container_name` 中第一个 `-` 之前的部分，无 `-` 则为 `other`。

### 4.3 命令行参数

| 参数 | 说明 |
|------|------|
| `results_dir` | 可选，结果目录，用于自动查找 CSV |
| `--locust-file` | Locust stats_history CSV 路径 |
| `--resource-files` | 一个或多个资源 CSV 路径 |
| `--output-dir` | 图表输出目录，默认 `plots` |

---

## 5. 数据流概览

```
┌─────────────────┐     *_stats_history.csv     ┌──────────────┐
│     Locust      │ ──────────────────────────► │              │
│   (压测执行)     │                              │  analyze.py  │
└─────────────────┘                              │  (数据分析)   │
                                                 │              │
┌─────────────────┐  resource_stats_*.csv        │              │
│   monitor.py    │ ──────────────────────────► │              │
│  (资源采集)      │                              └──────┬───────┘
└─────────────────┘                                     │
                                                        ▼
                                               latency_p50_p95.png
                                               throughput_rps.png
                                               cpu_usage_*.png
                                               memory_usage_*.png
                                               network_io_*.png
                                               disk_io_*.png
```

---

## 6. 兼容性说明

- **Locust**：只要压测脚本通过 `events.request.fire` 或 Locust 内置统计上报数据，且最终 CSV 含 `Timestamp`、`Total Median Response Time`、`Total 95%`、`Requests/s`，即可被 `analyze.py` 使用。
- **monitor.py**：依赖 Docker SDK，需能访问目标宿主机的 Docker 守护进程；输出 CSV 列名需与上述规范一致。
- **analyze.py**：依赖 `pandas`、`matplotlib`；仅依赖上述 CSV 接口，不依赖具体 Agent 或业务逻辑。
