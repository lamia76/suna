# 压测脚本延展性说明

本文档说明 Suna 压测脚本是否可延展用于其他 AI Agent，以及如何适配。

## 结论

**可以延展**，但需要根据目标 Agent 的 API 结构做相应适配。主要差异集中在 `locustfile.py` 中。

---

## 可复用的部分

| 组件 | 复用度 | 说明 |
|------|--------|------|
| **Locust 框架** | 高 | 压测框架本身是通用的 |
| **analyze.py** | 高 | Locust 导出的 CSV 为标准格式；资源监控只要列名一致即可 |
| **monitor.py** | 高 | 基于 Docker 容器采集指标，与具体 Agent 无关 |

---

## 需按 Agent 适配的部分（主要在 `locustfile.py`）

| 项目 | Suna 当前实现 | 其他 Agent 可能不同 |
|------|---------------|---------------------|
| **认证** | `SUNA_API_KEY` + `x-api-key` | 可能是 `Authorization: Bearer` 等 |
| **会话/线程** | `POST /api/threads` | 可能无会话概念，或为 `/conversations` 等 |
| **任务触发** | `POST /api/agent/start`（thread_id、prompt、model_name） | 可能是 `/api/chat`、`/v1/chat/completions` 等 |
| **轮询状态** | `GET /api/agent-run/{id}` | 可能是 WebSocket、SSE 或纯同步接口 |
| **终态判断** | `completed`、`failed`、`stopped`、`error` | 各 Agent 状态字段和取值可能不同 |

---

## 延展方案

1. **环境变量配置**：用 `API_BASE_URL`、`API_KEY`、`ENDPOINT_START`、`ENDPOINT_POLL` 等替代硬编码
2. **配置文件（JSON/YAML）**：定义 base_url、endpoints、payload 模板、terminal_status，由脚本加载
3. **可插拔适配器**：抽象 `SunaUser` 为通用 `AgentLoadTestUser`，通过配置或策略模式注入不同 Agent 的 API 适配逻辑

只要目标 Agent 具备「发起任务 → 轮询/等待 → 结束」的流程，现有脚本框架即可复用，主要工作量在 API 路径、认证与 payload 的配置化。
