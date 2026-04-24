# LangGraph 文本/语音进线录日志（Agent Chat）— Design Spec
Date: 2026-04-24
Status: Draft (pending product review)

## Overview

在现有 **FastAPI + LangChain 直连** 的 `agent_service.chat` 上，用 **LangGraph** 重构图内控制流，使「意图路由 → 饮食/运动/闲聊 → 多轮补全 → 待确认草稿 → 确认/取消落库」成为**显式节点与可测试状态**，**不改变**对外 HTTP 形状（`POST /api/v1/agent/chat` 等）与 `ChatIn` / `ChatOut` 契约。

**明确排除在首版 Graph 之外**：拍照上传、视觉填表、弹窗后点击添加——该链路保持**独立端点**与现有前后端产品流程；若与落库/校验有重复，仅抽**可复用函数**，不合并为一张大物理图。

---

## 1. Goals

| 目标 | 说明 |
|------|------|
| **B** | 人机回环有清晰 **`state` / phase** 模型，单测可针对节点与边断言，不依赖通读 400+ 行 `if` 顺序。 |
| **A** | 持续采用 **会话级** 状态：与现网一致，**Redis** 存 pending / confirm 草稿，TTL（默认 1800s），**不**要求首版上 LangGraph 全量跨进程 **checkpoint 持久化**。 |
| **D** | 与 `pyproject` / README 中「LangGraph」描述对齐；**删未用依赖或落地使用**在实现阶段二选一。 |

## 2. Non-goals (首版)

- 将 **Banner**、**昨日总结 (insight)** 并入本图；后续可**另建图**或**共享子节点库**。
- 拍照/图片识别进线（独立 API + 弹窗确认）。
- 跨天、跨设备「严格同一 LangGraph trace 续跑」的分布式 checkpoint 语义。

---

## 3. Current behavior (基线，便于 diff)

实现集中在 `app/services/agent_service.py` 的 `chat`；多轮与待确认状态由 `app/services/chat_pending_service.py` 以 Redis 键维护：

- `intake_chat:pending` / `intake_chat:confirm`：饮食多轮、饮食确认稿。
- `burn_chat:pending` / `burn_chat:confirm`：运动多轮、运动确认稿。

`chat` 的**显式状态机**可概括为（顺序有优先级）：

1. 若存在**饮食确认稿**：解析「确认/取消」→ 落库或清空；否则在「可切闲聊」时清状态并 `generate_general_advice`；否则重发预览。
2. 若存在**运动确认稿**：同上，落库为 `burn_service.create_burn` 等。
3. 同时存在 `burn_pending` 与 `intake_pending` 时清运动 pending（现行为）。
4. 否则用 `burn_pending` / `intake_pending` 拼出 `route_ctx`，`route_chat_intent` 分支为 **general** / **log_burn** / **log_intake**。
5. `general` → `clear_all_chat_state` + 一般建议；`log_burn` / `log_intake` 走 `burn_agent` / `diet_agent` 的 extract 与 normalize，经 **need_clarify** 写回 pending 或经校验后写 **confirm 草稿** 并返回预览。

LLM 仍来自 `diet_agent._get_llm` / 各 `extract_*`；本设计**不**要求首版重写 prompt，仅**搬迁编排**。

---

## 4. Proposed graph shape（逻辑节点）

以下为**与现行为 1:1 对齐**的推荐节点分解（名字可在实现中缩短）：

| 逻辑节点 | 职责 | 现代码对应关系 |
|----------|------|----------------|
| `load_context` | 读 Redis：确认稿 / 补全 context / 决定本轮 `user_text` 与 `route_ctx` 构造方式 | `chat` 前段若干 `get_*` |
| `resolve_confirm` | 若存在饮食或运动确认稿，解析 `confirm`/`cancel` 或重路由到 general | 确认分支整块 |
| `commit_intake` / `commit_burn` | 在确认时写 DB，清空 Redis | `_handle_add_log` + `burn_service.create_burn` 循环 |
| `route_intent` | 无待确认时，`route_chat_intent(route_ctx)` | `routed` |
| `advise_general` | `generate_general_advice` | `general` 分支 |
| `extract_burn` | `extract_burn_chat` + `normalize` + 分支 need_clarify / 填 confirm | `log_burn` 支路 |
| `extract_intake` | `extract_intake_chat` + `normalize` + 校验 + 填 confirm | `log_intake` 支路 |
| `reply_preview` / `reply_clarify` | 构造 `ChatOut.reply` | 多处 `return ChatOut` |

**边**：以 `routed.intent`、`confirm_draft` 存在性、`extraction.flow` 等为条件，与现 `if` 顺序一致；实现时用 LangGraph 的**条件边**或**单节点内 switch**（优先可读性，其次「节点数少」）。

---

## 5. State 与「暂停」

**Graph 内 TypedDict/Schema** 建议显式包含（与测试契约对齐，可与 Redis 内容对照）：

- `user_id`, `session_id`（与 Redis key 一致）
- `message`：本轮用户文本（NLS/客户端传入）
- `body_block`：体征上下文（`format_user_body_context`）
- `phase` 或等价枚举：如 `idle` | `intake_clarify` | `intake_confirm` | `burn_clarify` | `burn_confirm`（**不必**新造 DB 表，**可与 Redis 有内容互相推导**）
- `routed`（`ChatIntentRoute`）
- 抽取结果：`IntakeChatExtraction` / burn 的规范化结构
- `reply: str`：本轮返回给前端的 `ChatOut.reply`
- 错误/业务异常码（可映射到 `BusinessException`）

**「暂停 / 下轮再进」（选项 A）**

- 首版推荐：**不依赖** LangGraph 内置 `interrupt` 的强制落地；保持 **请求结束于「写 Redis + 返回 reply」**。
- 下一请求**同一** `user_id` + `session_id` 再次 `invoke` / `ainvoke` 入口节点，**Redis 即「外部化 checkpoint」**。
- 若未来需要「单 API 长连接内 interrupt」，再评估 `interrupt_before` + 可插拔 **CheckpointSaver**（如 Postgres/SQLite），**不改变**本 spec 的节点语义。

`thread_id` 可约定为 `f"{user_id}:{session_id or 'default'}"`，与 Redis 分片一致。

---

## 6. API 与测试

- **HTTP**：保持 **现有** `chat(payload)` 的入参/出参；实现上可为「薄包装：`chat` 调用 `graph.ainvoke`」或 **graph 内嵌** 原逻辑，**对外零破坏**。
- **单元测试**：对**节点级纯函数**（如「给定 state + mock DB，产出的 reply 与 Redis 调用」）用 fixture；对 **confirm 关键词解析**、**多轮 key 的读写**做表驱动测试。现有与 `agent_service` 集成的用例在迁移后**应继续绿**，必要时**复制为图级**集成测试。

---

## 7. Error handling

- `route_chat_intent` / `extract_*` 失败时与现网一致：日志降级、部分路径回落到 `generate_general_advice` 等（**不**在首版改产品语义）。
- 确认落库 **try/except** 保持 `AGENT_INVOKE_FAILED` 等行为。

---

## 8. Phased delivery

1. **Phase 1**：仅重构 `app/services/agent_service.py` 内编排为 `StateGraph`（或编译图 + 单入口），`diet_agent` / `burn_agent` 保持**函数级**调用。
2. **Phase 2**（可选）：将公共「落库+校验」抽到 `app/graphs/persist_nodes.py` 等，供未来 Banner/insight 复用**风格**，非强制同图。
3. **依赖**：若 Graph 为唯一使用处，在评审后更新 `README` 与**死依赖**（`langgraph` 已声明则落实 import）。

---

## 9. Spec self-review

- **Placeholder**：无 TBD；**拍照** 已明确出范围。
- **一致性**：与 `chat_pending_service` 键名及 `chat` 优先顺序与仓库现状一致；若之后改业务顺序，**须同步**图边与单测。
- **范围**：单 spec 只覆盖「语音/文本 agent chat 图化」；Banner/insight 为**独立**后续。
- **歧义**：「Graph」首版=**控制流在 LangGraph 中**；**持久化**仍以 Redis 为准，不暗示启用 LangGraph Server。

---

## 10. Changelog

- 2026-04-24: Initial spec from brainstorming（目标 B+A+D，首图范围=文本/语音；拍照独立）。
