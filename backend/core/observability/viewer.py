"""
通用 Agent 性能数据统计脚本

支持不同 agent 类型的指标分析，通过配置指定：
- 排除的工具（从通用工具统计中排除，由专项分析器处理）
- 上下文管理工具（可选，用于 context 专项分析）
- 内存管理工具（可选，用于 memory 专项分析）
- 事件类型映射、字段映射（可扩展以支持不同日志格式）

用法:
  python -m core.observability.viewer --file path/to/metrics.jsonl
  python -m core.observability.viewer --agent-type agentpress   # 使用 AgentPress 预设
  python -m core.observability.viewer --agent-type generic      # 通用模式（无排除）
  python -m core.observability.viewer --config agent_config.json  # 自定义配置
"""

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
import argparse

LOG_FILE = "metrics_logs.jsonl"

# --- 预设配置 ---
AGENT_PRESETS: Dict[str, Dict[str, Any]] = {
    "agentpress": {
        "description": "AgentPress 预设：排除任务/内存工具，做专项分析",
        "excluded_tools": {"create_tasks", "update_tasks", "view_tasks", "complete", "manage_core_memory"},
        "context_tools": {"create_tasks", "update_tasks", "view_tasks", "complete"},
        "memory_tools": {"manage_core_memory"},
        "event_types": {
            "tool_execution": "tool_execution",
            "llm_call": "llm_call",
            "agent_execution": "agent_execution",
            "agent_sandbox": "agent_sandbox",
        },
        "field_mapping": {
            "tool_name": "tool_name",
            "duration_ms": "duration_ms",
            "success": "success",
            "model": "model",
            "prompt_tokens": "prompt_tokens",
            "completion_tokens": "completion_tokens",
        },
    },
    "generic": {
        "description": "通用预设：不排除任何工具，适用于任意 agent",
        "excluded_tools": set(),
        "context_tools": None,  # 不启用 context 专项分析
        "memory_tools": None,   # 不启用 memory 专项分析
        "event_types": {
            "tool_execution": "tool_execution",
            "llm_call": "llm_call",
            "agent_execution": "agent_execution",
            "agent_sandbox": "agent_sandbox",
        },
        "field_mapping": {
            "tool_name": "tool_name",
            "duration_ms": "duration_ms",
            "success": "success",
            "model": "model",
            "prompt_tokens": "prompt_tokens",
            "completion_tokens": "completion_tokens",
        },
    },
}


@dataclass
class ViewerConfig:
    """Viewer 运行配置"""

    excluded_tools: Set[str] = field(default_factory=set)
    context_tools: Optional[Set[str]] = None
    memory_tools: Optional[Set[str]] = None
    event_types: Dict[str, str] = field(default_factory=lambda: {
        "tool_execution": "tool_execution",
        "llm_call": "llm_call",
        "agent_execution": "agent_execution",
        "agent_sandbox": "agent_sandbox",
    })
    field_mapping: Dict[str, str] = field(default_factory=lambda: {
        "tool_name": "tool_name",
        "duration_ms": "duration_ms",
        "success": "success",
        "model": "model",
        "prompt_tokens": "prompt_tokens",
        "completion_tokens": "completion_tokens",
    })

    def get(self, data: Dict, key: str, default: Any = None) -> Any:
        """根据 field_mapping 从 data 取字段值"""
        mapped = self.field_mapping.get(key, key)
        return data.get(mapped, default)

    @classmethod
    def from_preset(cls, name: str) -> "ViewerConfig":
        preset = AGENT_PRESETS.get(name)
        if not preset:
            raise ValueError(f"Unknown preset: {name}. Available: {list(AGENT_PRESETS.keys())}")
        d = preset.copy()
        return cls(
            excluded_tools=set(d.get("excluded_tools", [])),
            context_tools=set(d["context_tools"]) if d.get("context_tools") else None,
            memory_tools=set(d["memory_tools"]) if d.get("memory_tools") else None,
            event_types=d.get("event_types", AGENT_PRESETS["generic"]["event_types"].copy()),
            field_mapping=d.get("field_mapping", AGENT_PRESETS["generic"]["field_mapping"].copy()),
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ViewerConfig":
        return cls(
            excluded_tools=set(d.get("excluded_tools", [])),
            context_tools=set(d["context_tools"]) if d.get("context_tools") else None,
            memory_tools=set(d["memory_tools"]) if d.get("memory_tools") else None,
            event_types=d.get("event_types", AGENT_PRESETS["generic"]["event_types"].copy()),
            field_mapping=d.get("field_mapping", AGENT_PRESETS["generic"]["field_mapping"].copy()),
        )


def load_config(config_path: str) -> ViewerConfig:
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ViewerConfig.from_dict(data)


def load_logs(log_file: str) -> List[Dict]:
    logs = []
    if not os.path.exists(log_file):
        print(f"No log file found at {log_file}")
        return []

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return logs


def analyze_tools(logs: List[Dict], config: ViewerConfig) -> None:
    et_tool = config.event_types["tool_execution"]
    tool_stats = defaultdict(lambda: {"count": 0, "total_duration": 0, "errors": 0})

    for log in logs:
        if log.get("event_type") != et_tool:
            continue
        data = log.get("data", {})
        name = config.get(data, "tool_name", "unknown")
        if name in config.excluded_tools:
            continue

        duration = config.get(data, "duration_ms") or 0
        success = config.get(data, "success")
        if success is None:
            success = True

        tool_stats[name]["count"] += 1
        tool_stats[name]["total_duration"] += float(duration)
        if not success:
            tool_stats[name]["errors"] += 1

    print("\n--- Tool Execution Statistics (General) ---")
    print(f"{'Tool Name':<40} {'Count':<10} {'Total Dur (ms)':<15} {'Avg Dur (ms)':<15} {'Errors':<10}")
    print("-" * 100)
    for name, stats in sorted(tool_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        avg = stats["total_duration"] / stats["count"] if stats["count"] > 0 else 0
        print(f"{name:<40} {stats['count']:<10} {stats['total_duration']:<15.2f} {avg:<15.2f} {stats['errors']:<10}")


def analyze_llm(logs: List[Dict], config: ViewerConfig) -> None:
    et_llm = config.event_types["llm_call"]
    llm_stats = defaultdict(lambda: {
        "count": 0, "total_duration": 0, "total_tokens": 0, "errors": 0,
        "breakdown": defaultdict(int),
    })

    for log in logs:
        if log.get("event_type") != et_llm:
            continue
        data = log.get("data", {})
        model = config.get(data, "model", "unknown")
        duration = config.get(data, "duration_ms") or 0
        success = config.get(data, "success")
        if success is None:
            success = True
        tokens = (config.get(data, "prompt_tokens") or 0) + (config.get(data, "completion_tokens") or 0)

        breakdown = data.get("token_breakdown")
        if breakdown:
            for k, v in breakdown.items():
                llm_stats[model]["breakdown"][k] += v

        llm_stats[model]["count"] += 1
        llm_stats[model]["total_duration"] += float(duration)
        llm_stats[model]["total_tokens"] += tokens
        if not success:
            llm_stats[model]["errors"] += 1

    print("\n--- LLM Statistics ---")
    print(f"{'Model Name':<40} {'Count':<10} {'Total Dur (ms)':<15} {'Avg Dur (ms)':<15} {'Avg Tokens':<15} {'Errors':<10}")
    print("-" * 115)
    for name, stats in sorted(llm_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        avg_dur = stats["total_duration"] / stats["count"] if stats["count"] > 0 else 0
        avg_tok = stats["total_tokens"] / stats["count"] if stats["count"] > 0 else 0
        print(f"{name:<40} {stats['count']:<10} {stats['total_duration']:<15.2f} {avg_dur:<15.2f} {avg_tok:<15.0f} {stats['errors']:<10}")
        if stats["breakdown"] and stats["total_tokens"] > 0:
            print("  Token Breakdown (Avg per call):")
            for k, v in sorted(stats["breakdown"].items(), key=lambda x: x[1], reverse=True):
                avg_k = v / stats["count"]
                pct = (v / stats["total_tokens"]) * 100
                print(f"    - {k:<25} {avg_k:<10.0f} ({pct:.1f}%)")
            print()


def analyze_agent(logs: List[Dict], config: ViewerConfig) -> None:
    et_agent = config.event_types["agent_execution"]
    agent_logs = [l for l in logs if l.get("event_type") == et_agent]
    print("\n--- Agent Execution Summary ---")
    print(f"Total Agent Runs: {len(agent_logs)}")
    if agent_logs:
        total = sum(config.get(l.get("data", {}), "duration_ms", 0) for l in agent_logs)
        avg = total / len(agent_logs)
        print(f"Total Run Duration: {total:.2f} ms")
        print(f"Average Run Duration: {avg:.2f} ms")


def analyze_sandbox(logs: List[Dict], config: ViewerConfig) -> None:
    et_sandbox = config.event_types["agent_sandbox"]
    sandbox_logs = [l for l in logs if l.get("event_type") == et_sandbox]
    print("\n--- Sandbox Statistics ---")
    if not sandbox_logs:
        print("No sandbox events found.")
        return

    actions = defaultdict(lambda: {"count": 0, "total_duration": 0, "errors": 0})
    for log in sandbox_logs:
        data = log.get("data", {})
        action = data.get("action", "unknown")
        duration = config.get(data, "duration_ms") or 0
        details = data.get("details", {})
        success = details.get("success", True)

        actions[action]["count"] += 1
        actions[action]["total_duration"] += float(duration)
        if not success:
            actions[action]["errors"] += 1

    print(f"{'Action':<30} {'Count':<10} {'Total Dur (ms)':<15} {'Avg Dur (ms)':<15} {'Errors':<10}")
    print("-" * 90)
    for action, stats in sorted(actions.items(), key=lambda x: x[1]["count"], reverse=True):
        avg = stats["total_duration"] / stats["count"] if stats["count"] > 0 else 0
        print(f"{action:<30} {stats['count']:<10} {stats['total_duration']:<15.2f} {avg:<15.2f} {stats['errors']:<10}")


def analyze_context(logs: List[Dict], config: ViewerConfig) -> None:
    if config.context_tools is None:
        return
    et_tool = config.event_types["tool_execution"]
    ctx_logs = [
        l for l in logs
        if l.get("event_type") == et_tool and config.get(l.get("data", {}), "tool_name") in config.context_tools
    ]
    print("\n--- Context Management Statistics (Tasks) ---")
    if not ctx_logs:
        print("No context/task management events found.")
        return

    total_count = len(ctx_logs)
    total_duration = sum(config.get(l.get("data", {}), "duration_ms", 0) for l in ctx_logs)
    avg_duration = total_duration / total_count if total_count > 0 else 0

    print(f"Total Context Operations: {total_count}")
    print(f"Total Duration: {total_duration:.2f} ms")
    print(f"Average Duration: {avg_duration:.2f} ms")

    tool_stats = defaultdict(lambda: {"count": 0, "duration": 0})
    for l in ctx_logs:
        name = config.get(l.get("data", {}), "tool_name", "unknown")
        tool_stats[name]["count"] += 1
        tool_stats[name]["duration"] += config.get(l.get("data", {}), "duration_ms", 0)

    print("\nBreakdown by Operation:")
    print(f"{'Operation':<20} {'Count':<10} {'Total Dur (ms)':<15} {'Avg Dur (ms)':<15}")
    print("-" * 65)
    for name, stats in sorted(tool_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        avg = stats["duration"] / stats["count"]
        print(f"{name:<20} {stats['count']:<10} {stats['duration']:<15.2f} {avg:<15.2f}")


def analyze_memory(logs: List[Dict], config: ViewerConfig) -> None:
    if config.memory_tools is None:
        return
    et_tool = config.event_types["tool_execution"]
    mem_logs = [
        l for l in logs
        if l.get("event_type") == et_tool and config.get(l.get("data", {}), "tool_name") in config.memory_tools
    ]
    print("\n--- Memory Management Statistics ---")
    if not mem_logs:
        print("No memory management events found.")
        return

    total_count = len(mem_logs)
    total_duration = sum(config.get(l.get("data", {}), "duration_ms", 0) for l in mem_logs)
    avg_duration = total_duration / total_count if total_count > 0 else 0

    print(f"Total Memory Operations: {total_count}")
    print(f"Total Duration: {total_duration:.2f} ms")
    print(f"Average Duration: {avg_duration:.2f} ms")

    tool_stats = defaultdict(lambda: {"count": 0, "duration": 0})
    for l in mem_logs:
        name = config.get(l.get("data", {}), "tool_name", "unknown")
        tool_stats[name]["count"] += 1
        tool_stats[name]["duration"] += config.get(l.get("data", {}), "duration_ms", 0)

    print("\nBreakdown by Operation:")
    print(f"{'Operation':<20} {'Count':<10} {'Total Dur (ms)':<15} {'Avg Dur (ms)':<15}")
    print("-" * 65)
    for name, stats in sorted(tool_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        avg = stats["duration"] / stats["count"]
        print(f"{name:<20} {stats['count']:<10} {stats['duration']:<15.2f} {avg:<15.2f}")


def analyze_performance(logs: List[Dict], config: ViewerConfig) -> None:
    if not logs:
        return

    sorted_logs = sorted(logs, key=lambda x: x.get("timestamp", ""))
    if not sorted_logs:
        return

    start_time = datetime.fromisoformat(sorted_logs[0]["timestamp"].replace("Z", "+00:00"))
    end_time = datetime.fromisoformat(sorted_logs[-1]["timestamp"].replace("Z", "+00:00"))
    total_duration_ms = (end_time - start_time).total_seconds() * 1000

    def get_intervals(event_type: str):
        intervals = []
        for log in logs:
            if log.get("event_type") != event_type:
                continue
            end = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
            duration = config.get(log.get("data", {}), "duration_ms", 0) or 0
            start = end - timedelta(milliseconds=duration)
            intervals.append((start, end))
        return intervals

    et_llm = config.event_types["llm_call"]
    et_tool = config.event_types["tool_execution"]
    et_sandbox = config.event_types["agent_sandbox"]

    llm_intervals = get_intervals(et_llm)
    tool_intervals = get_intervals(et_tool)
    sandbox_intervals = get_intervals(et_sandbox)

    total_llm_raw_ms = sum(config.get(l.get("data", {}), "duration_ms", 0) or 0 for l in logs if l.get("event_type") == et_llm)
    total_tool_raw_ms = sum(config.get(l.get("data", {}), "duration_ms", 0) or 0 for l in logs if l.get("event_type") == et_tool)
    total_sandbox_raw_ms = sum(config.get(l.get("data", {}), "duration_ms", 0) or 0 for l in logs if l.get("event_type") == et_sandbox)

    def merge_intervals(intervals):
        if not intervals:
            return []
        intervals = sorted(intervals, key=lambda x: x[0])
        merged = [intervals[0]]
        for cur in intervals[1:]:
            last = merged[-1]
            if cur[0] < last[1]:
                merged[-1] = (last[0], max(last[1], cur[1]))
            else:
                merged.append(cur)
        return merged

    def calc_duration(intervals):
        merged = merge_intervals(intervals)
        return sum((e - s).total_seconds() * 1000 for s, e in merged)

    all_intervals = llm_intervals + tool_intervals + sandbox_intervals
    total_active_ms = calc_duration(all_intervals)
    system_overhead_ms = max(0, total_duration_ms - total_active_ms)

    merged_llm = merge_intervals(llm_intervals)
    merged_tool = merge_intervals(tool_intervals)
    overlap_ms = 0
    for ls, le in merged_llm:
        for ts, te in merged_tool:
            latest_start = max(ls, ts)
            earliest_end = min(le, te)
            if latest_start < earliest_end:
                overlap_ms += (earliest_end - latest_start).total_seconds() * 1000

    print("\n--- End-to-End Performance Statistics ---")
    print(f"Total Session Duration: {total_duration_ms / 1000:.2f} s")
    print("\nComponent Durations (Independent & Raw):")
    print(f"- LLM Call Duration: {total_llm_raw_ms / 1000:.2f} s")
    print(f"- Tool Execution Duration: {total_tool_raw_ms / 1000:.2f} s")
    print(f"- Sandbox Execution Duration: {total_sandbox_raw_ms / 1000:.2f} s")
    print("\nAnalysis:")
    print(f"- Sum of LLM & Tool: {(total_llm_raw_ms + total_tool_raw_ms) / 1000:.2f} s")
    print(f"- Calculated Overlap (LLM & Tool): {overlap_ms / 1000:.2f} s")
    if overlap_ms > 0:
        print(f"  (Note: {overlap_ms / 1000:.2f}s of Tool Execution occurred during LLM Streaming)")
    print("\nSystem Breakdown:")
    print(f"- Effective Active Time (Union of all events): {total_active_ms / 1000:.2f} s")
    print(f"- Other System Overhead: {system_overhead_ms / 1000:.2f} s")
    print(f"\nStart Time: {sorted_logs[0]['timestamp']}")
    print(f"End Time: {sorted_logs[-1]['timestamp']}")


def run_analyzers(logs: List[Dict], config: ViewerConfig) -> None:
    """运行所有分析器"""
    analyze_performance(logs, config)
    analyze_agent(logs, config)
    analyze_context(logs, config)
    analyze_memory(logs, config)
    analyze_sandbox(logs, config)
    analyze_llm(logs, config)
    analyze_tools(logs, config)


def resolve_log_file(file_arg: Optional[str]) -> str:
    if file_arg:
        return file_arg
    logs_dir = os.path.join(os.getcwd(), "logs")
    if os.path.exists(logs_dir):
        log_files = []
        pattern = re.compile(r"^metrics_logs_(\d{8}_\d{6})\.jsonl$")
        for f in os.listdir(logs_dir):
            if f == "metrics_logs.jsonl":
                log_files.append((f, ""))
            else:
                m = pattern.match(f)
                if m:
                    log_files.append((f, m.group(1)))
        if log_files:
            latest = sorted(log_files, key=lambda x: x[1])[-1][0]
            path = os.path.join(logs_dir, latest)
            print(f"Using latest log file: {path}")
            return path
    return LOG_FILE


def main() -> None:
    parser = argparse.ArgumentParser(
        description="通用 Agent 性能数据统计脚本，支持不同 agent 类型的指标分析"
    )
    parser.add_argument("--file", "-f", help="Path to jsonl log file")
    parser.add_argument("--trace-id", "-t", help="Filter by specific trace ID")
    parser.add_argument(
        "--agent-type",
        "-a",
        choices=list(AGENT_PRESETS.keys()),
        default="agentpress",
        help=f"Preset config. Default: agentpress. Options: {', '.join(AGENT_PRESETS.keys())}",
    )
    parser.add_argument("--config", "-c", help="Path to custom JSON config file (overrides --agent-type)")
    args = parser.parse_args()

    if args.config:
        config = load_config(args.config)
        print(f"Loaded config from: {args.config}")
    else:
        config = ViewerConfig.from_preset(args.agent_type)
        print(f"Using preset: {args.agent_type}")

    log_file = resolve_log_file(args.file)
    logs = load_logs(log_file)

    if not logs:
        print("No logs found.")
        return

    traces: Dict[str, List[Dict]] = defaultdict(list)
    for log in logs:
        trace_id = log.get("trace_id") if log.get("trace_id") is not None else "unknown"
        traces[trace_id].append(log)

    if args.trace_id:
        if args.trace_id not in traces:
            print(f"Trace ID '{args.trace_id}' not found.")
            return
        print(f"\n{'=' * 80}")
        print(f"ANALYSIS FOR TRACE: {args.trace_id}")
        print(f"{'=' * 80}")
        run_analyzers(traces[args.trace_id], config)
        return

    print(f"\nFound {len(traces)} traces:")
    print(f"{'Trace ID':<40} {'Events':<10} {'Start Time':<30} {'Duration (s)':<15}")
    print("-" * 100)

    sorted_trace_ids = []
    for trace_id, trace_logs in traces.items():
        sl = sorted(trace_logs, key=lambda x: x.get("timestamp", ""))
        if not sl:
            continue
        st = datetime.fromisoformat(sl[0]["timestamp"].replace("Z", "+00:00"))
        et = datetime.fromisoformat(sl[-1]["timestamp"].replace("Z", "+00:00"))
        duration = (et - st).total_seconds()
        print(f"{str(trace_id):<40} {len(trace_logs):<10} {sl[0]['timestamp']:<30} {duration:<15.2f}")
        sorted_trace_ids.append((trace_id, st))

    sorted_trace_ids.sort(key=lambda x: x[1])

    for trace_id, _ in sorted_trace_ids:
        print(f"\n\n{'#' * 100}")
        print(f"TRACE: {trace_id}")
        print(f"{'#' * 100}")
        run_analyzers(traces[trace_id], config)


if __name__ == "__main__":
    main()
