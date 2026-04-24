# LangGraph 编排、多意图与用户画像 — Design Spec

Date: 2026-04-24

## Overview

将当前基于 `agent_service.chat()` 中条件分支与 `chat_pending_service` 的多轮对话流程，迁移为 **LangGraph** 编排：**Supervisor 路由 + 子图**，在写库前通过 **`interrupt` + 用户确认** 实现 human-in-the-loop。扩展意图：在既有「闲聊 / 摄入记录 / 消耗记录」之上增加 **聊天内提议修改身体指标**、**聊天内确认写入个性化偏好**（如忌口）。身体指标与设置页 **同源**（`users` 表）；个性化 **仅通过聊天确认落库**，**设置页不展示**偏好内容，仅在模型侧注入摘要以提升建议相关性。

---

## Product constraints (agreed)

| 维度 | 结论 |
|------|------|
| Human in the loop | 仅终端用户：写入或变更前有确认或取消（可多轮澄清）；无运营审核队列。 |
| 身体数据 | 以设置页 / REST 为主；聊天可提议修改，确认后写入 **与 REST 相同的 `users` 字段**。 |
| 个性化（忌口等） | 通过聊天抽取并 **确认后** 写入新表；设置页 **不展示、不编辑** 该类数据；用于 prompt 上下文，**不要求**单独设置 UI。 |
| API | 仍以 `POST /agent/chat` 为主；`thread_id` 建议 `user_id` + `session_id`；第一期可继续用自然语言「确认/取消」，与现有 `_parse_confirm_intent` 行为对齐。 |

---

## 1. Architecture

### 1.1 Components

1. **`ChatGraph`（编译后的 LangGraph）**
   - **输入**：`user_id`、`session_id`、本轮 `message`；可选后续扩展 `resume` / 结构化 command（第一期可不强制）。
   - **状态**：消息列表、当前路由意图、各子图私有字段（如摄入/消耗草案、身体补丁草案、偏好条目草案）、`hitl_phase`（如 `idle` / `awaiting_confirm`）。
   - **输出**：`reply` 文本、是否处于 `interrupt` 等待用户；可选最小元数据（如 `needs_user_input`），**不向客户端返回完整偏好表**。

2. **Persistence**
   - **业务真源**：`users` 表（身高、体重、年龄、性别等）；新建 **`user_preference`（或等价命名）多行表** 存确认后的偏好原文与分类。
   - **图状态**：LangGraph **checkpointer**（优先与现有基础设施一致，例如 Redis；或 PostgresSaver）。`thread_id = f"{user_id}:{session_id}"`（格式实现时可调整，须稳定可复现）。
   - **迁移**：短期允许图 checkpoint 与现有 `chat_pending_service` 并存；**目标态为单一 checkpoint 源**，减少双写。

3. **与 REST 的关系**
   - 设置页 / 用户更新 API **直接更新 `users`**，不经过图。
   - 聊天确认修改身体数据时调用 **同一套 user update service**，保证单真源。
   - 偏好 **仅聊天确认写入**；`format_user_body_context` 扩展为 **`format_user_context_for_model`**：身体摘要 + 从 DB 聚合的偏好短列表，仅注入 LLM。

4. **第一层意图（路由）**

   在现有 `general` / `log_intake` / `log_burn` 上扩展，例如：

   - `update_body_metrics` — 从自然语言抽取拟写入 `users` 的字段补丁 → 预览 → HITL。
   - `update_preferences` — 从自然语言抽取忌口/过敏等 → 预览 → HITL → 插入偏好表。

   路由输出保持 **轻量结构化 JSON**（与当前 `route_chat_intent` 模式一致），枚举与 prompt 同步更新。

5. **Human in the loop（LangGraph）**
   - 在即将写库前 **`interrupt`**，state 保留结构化草案与用户可见预览。
   - 下一轮：解析 `confirm` / `cancel` / 无法解析（保持预览或澄清），与现网 pending 体验对齐。
   - 确认后：`commit` 节点调用 `_handle_add_log`、`burn_service.create_burn`、user 更新、偏好插入。

### 1.2 Recommended graph shape

采用 **Supervisor + 子图**：顶层 `route_intent` → 各业务子图；**会改库的子图**统一进入 **present_confirm → interrupt_for_user**；恢复时走 **`hitl_resume`** → `commit` 或 `cancel`。新意图以 **新子图** 扩展，避免单图无限膨胀。

---

## 2. Data model and API

### 2.1 Body metrics

- **表**：`users`（已有 `height`、`weight`、`age`、`gender` 等）。
- **REST**：现有用户更新接口（如 `app/api/v1/user.py` + `UserUpdate`）继续为权威写入路径之一。
- **聊天**：`update_body_metrics` 子图仅产生 **草案**；确认后调用与 REST **相同的 service** 更新行。

### 2.2 Personalization storage

**推荐 MVP：多行表** `user_preference`（名称实现可微调）

| 列 | 说明 |
|----|------|
| `id` | PK |
| `user_id` | FK → `users.id`，索引 |
| `category` | 如 `dislike` / `allergy` / `other` |
| `raw_text` | 用户确认后落库的表述 |
| `normalized_key` | 可选，二期食材归一 |
| `created_at` / `updated_at` | 审计与时间 |

替代方案：1:1 `user_portrait.preferences_json` — 迭代更快，审计与增量略弱；若选需在实现计划中说明取舍。

### 2.3 HTTP contract

- **`POST /agent/chat`**：保持主入口；`ChatIn` 可 **可选** 增加与 LangGraph `Command(resume=...)` 对齐的字段；第一期 **默认仍用自然语言** 确认/取消。
- **无需**强制新增独立「确认接口」；若产品后续需要结构化按钮，再在 `ChatOut` 增加 `pending_action_id` 等字段。

---

## 3. Nodes, errors, and testing

### 3.1 Top-level flow

- **`ingest_message`**：合并本轮输入；处理从 `interrupt` 恢复时的上下文。
- **`route_intent`**：扩展后的意图分类。
- **条件边**：若 state 为 **`awaiting_confirm`**，**优先** `hitl_resume`，避免重复全量路由误伤。

### 3.2 Subgraphs and code reuse

| 子图 | 行为 | 结束 |
|------|------|------|
| `general` | `generate_general_advice` | 仅回复 |
| `intake` | `extract_intake_chat`、澄清、食物名校验 | 摄入草案 → HITL |
| `burn` | `extract_burn_chat`、澄清 | 消耗草案 → HITL |
| `body_metrics` | 新：`extract_body_patch`（或等价） | 预览 → HITL |
| `preferences` | 新：`extract_preference_items`（或等价） | 预览 → HITL |

预览文案：摄入/消耗复用 `_build_confirm_preview`、`_build_burn_preview`；身体与偏好使用新模板字符串。

### 3.3 HITL nodes

- **`present_confirm`**：生成预览。
- **`interrupt_for_user`**：`interrupt`，checkpoint 持久化草案。
- **`hitl_resume`**：`confirm` → 对应 commit；`cancel` → 清空并回复；歧义输入 → 与当前 pending 行为一致（重显预览或进入澄清）。

### 3.4 Error handling

- **路由 LLM 失败**：与现网一致，**默认 `log_intake`**（见 `agent_service.chat` 当前降级）。
- **抽取失败**：尝试 `generate_general_advice` 并清理本子图 pending。
- **写库失败**：返回用户可读错误；**建议保留 checkpoint 中的草案** 以便用户再次确认重试。
- **并发**：单 `thread_id` 按单会话串行假设；多客户端并发后续可加锁或队列。

### 3.5 Testing

- **路由**：对扩展枚举的单元测试（mock LLM 或固定 JSON）。
- **HITL**：`confirm` / `cancel` / 歧义输入 的集成测试（memory checkpointer + 测试用 DB）。
- **回归**：摄入/消耗确认流与 REST 更新身体字段行为与现网一致。

---

## 4. Out of scope (this spec)

- 运营后台审核、多用户协作编辑画像。
- 偏好食材全局本体与自动归一（可作为二期，仅预留 `normalized_key`）。
- 语音专用通道与非文本 interrupt 协议（可与其它 voice spec 另文合并时再对齐）。

---

## 5. Next step

实现前使用 **writing-plans** 产出分阶段迁移计划（依赖版本、checkpointer 选型、`chat_pending_service` 退役步骤、迁移与回滚）。
