# LangGraph 多意图、用户偏好与 HITL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 LangGraph（Supervisor + 子图 + `interrupt` 确认）替换 `agent_service.chat` 中的手写状态机；扩展意图与 `user_preference` 表；聊天确认写入偏好与身体补丁；`format_user_context_for_model` 注入模型上下文；默认 feature flag 安全切流。

**Architecture:** 顶层 `StateGraph` 按 `hitl_phase` 与 `pending_confirm_kind` 分流：`awaiting_confirm` 时先进 `hitl_resume`，否则 `route_intent` → 各子图。写库类子图在 `present_confirm` 后调用 `interrupt()`；下一轮用自然语言解析 `confirm`/`cancel`（复用 `_parse_confirm_intent` 语义）。Checkpointer 第一期用 `MemorySaver`（单测/本地）；生产可换 Redis/Postgres saver（见 Task 9）。`users` 身体字段仍由 `user_service.update_user` 写入。

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Redis（现有 `chat_pending_service` 在 flag 关闭时仍用）, LangGraph ≥0.2.40（已在 `pyproject.toml`）, LangChain Core, pytest + pytest-asyncio。

**Spec:** `docs/superpowers/specs/2026-04-24-langgraph-agent-hitl-design.md`

---

## File Map

**New**

| 文件 | 职责 |
|------|------|
| `app/models/user_preference.py` | `UserPreference` ORM（`user_id`, `category`, `raw_text`, `normalized_key` 可空） |
| `alembic/versions/<new>_add_user_preference.py` | 建表；`down_revision = 'e7f8a9b0c1d2'`（当前链头，若你本地 `alembic heads` 不同则先 `merge` 再改） |
| `app/schemas/body_patch.py` | `BodyMetricsPatch`（可选 `height`/`weight`/`age`/`gender`）、`BodyMetricsDraft`（补丁 + `clarify_message`/`flow`） |
| `app/schemas/preference_extraction.py` | `PreferenceItem`, `PreferenceExtraction`（`items`/`flow`/`clarify_message`） |
| `app/prompts/body_metrics_chat.py` | 身体补丁抽取 prompt 常量 |
| `app/prompts/preference_chat.py` | 偏好抽取 prompt 常量 |
| `app/services/user_preference_service.py` | `add_preferences`, `list_raw_texts_for_user`（或等价命名） |
| `app/graphs/diet_chat_state.py` | `DietChatState` TypedDict / dataclass 形状定义 |
| `app/graphs/diet_chat_graph.py` | `build_diet_chat_graph()` → 编译后的 `CompiledStateGraph` |
| `app/services/chat_graph_runner.py` | `run_chat_turn(...)`：组 `configurable`/`thread_id`，`ainvoke`，把图输出转成 `ChatOut` |
| `tests/test_chat_route_intent_parse.py` | 扩展意图 JSON 解析 |
| `tests/test_user_preference_service.py` | 偏好写入/列出（需 DB 或 mock，见任务内说明） |
| `tests/test_diet_chat_graph_hitl.py` | MemorySaver + mock LLM/节点 的 HITL 路径 |

**Modify**

| 文件 | 职责 |
|------|------|
| `app/schemas/chat_intent.py` | `ChatRouteIntent` 增加 `update_body_metrics`, `update_preferences` |
| `app/prompts/chat_intent_router.py` | 路由说明与 JSON 示例覆盖新意图 |
| `app/prompts/__init__.py` | 导出新 prompt（若需） |
| `app/agents/diet_agent.py` | `extract_body_metrics_chat`, `extract_preferences_chat`（与 `extract_intake_chat` 同模式） |
| `app/services/user_body_context.py` | 新增 `format_user_context_for_model(db, user) -> str`：身体 + 偏好摘要（异步查偏好） |
| `app/services/agent_service.py` | `USE_LANGGRAPH_CHAT` 为真时委托 `chat_graph_runner.run_chat_turn`；否则保持现状 |
| `app/core/config.py` | `USE_LANGGRAPH_CHAT: bool = False` |
| `app/models/__init__.py` | 导出 `UserPreference` |
| `app/api/v1/agent.py` | 无需改签名；若 `ChatOut` 增加可选字段可同步 |

---

## Task 1: `UserPreference` 模型与 Alembic 迁移

**Files:**

- Create: `app/models/user_preference.py`
- Create: `alembic/versions/<timestamp>_add_user_preference.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: 写失败测试（导入模型表名）**

Create `tests/test_user_preference_model.py`:

```python
from app.models.user_preference import UserPreference


def test_user_preference_tablename() -> None:
    assert UserPreference.__tablename__ == "user_preferences"
```

Run:

```bash
cd d:\AgentDemo\dietAgent_demo1
pytest tests/test_user_preference_model.py::test_user_preference_tablename -v
```

Expected: **FAIL** `ModuleNotFoundError` 或 `ImportError`（模型文件尚不存在）。

- [ ] **Step 2: 实现模型**

Create `app/models/user_preference.py`:

```python
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserPreference(Base, TimestampMixin):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_text: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

在 `app/models/__init__.py` 中 `from app.models.user_preference import UserPreference` 并加入 `__all__`（若项目使用该模式）。

- [ ] **Step 3: Alembic 迁移**

新建 revision，`down_revision` 设为当前 head（截至 spec 撰写为 `e7f8a9b0c1d2`；以 `uv run alembic heads` 为准）：

```python
"""add user_preferences table"""

revision = "<new_id>"
down_revision = "e7f8a9b0c1d2"  # 若不一致请替换为 alembic heads 输出

def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("raw_text", sa.String(512), nullable=False),
        sa.Column("normalized_key", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_table("user_preferences")
```

Run（需本地 Postgres）:

```bash
uv run alembic upgrade head
```

Expected: **SUCCESS**，无报错。

- [ ] **Step 4: 再跑 Step 1 测试**

Expected: **PASS**

- [ ] **Step 5: Commit**

```bash
git add app/models/user_preference.py app/models/__init__.py alembic/versions/ tests/test_user_preference_model.py
git commit -m "feat: add user_preferences model and migration"
```

---

## Task 2: 扩展 `ChatRouteIntent` 与解析测试

**Files:**

- Modify: `app/schemas/chat_intent.py`
- Create: `tests/test_chat_route_intent_parse.py`

- [ ] **Step 1: 失败测试**

`tests/test_chat_route_intent_parse.py`:

```python
import json

import pytest

from app.agents.diet_agent import parse_intent_route_json
from app.schemas.chat_intent import ChatRouteIntent


@pytest.mark.parametrize(
    "intent_str",
    ["update_body_metrics", "update_preferences"],
)
def test_parse_extended_intents(intent_str: str) -> None:
    raw = json.dumps({"intent": intent_str})
    got = parse_intent_route_json(raw)
    assert got.intent == ChatRouteIntent(intent_str)
```

Run:

```bash
pytest tests/test_chat_route_intent_parse.py -v
```

Expected: **FAIL**（枚举无新值或校验错误）。

- [ ] **Step 2: 修改枚举**

在 `app/schemas/chat_intent.py` 的 `ChatRouteIntent` 中增加：

```python
    update_body_metrics = "update_body_metrics"
    update_preferences = "update_preferences"
```

- [ ] **Step 3: 再跑测试**

Expected: **PASS**

- [ ] **Step 4: 更新路由 prompt**

在 `app/prompts/chat_intent_router.py` 中补充新意图的中文说明与示例 JSON，明确要求 `intent` 只能是扩展后的枚举值之一（含 `general`/`log_intake`/`log_burn`）。

- [ ] **Step 5: Commit**

```bash
git add app/schemas/chat_intent.py app/prompts/chat_intent_router.py tests/test_chat_route_intent_parse.py
git commit -m "feat: extend chat route intents for body and preferences"
```

---

## Task 3: 偏好服务与模型上下文

**Files:**

- Create: `app/services/user_preference_service.py`
- Modify: `app/services/user_body_context.py`

- [ ] **Step 1: 失败测试**

`tests/test_user_preference_service.py`（若暂无 async DB fixture，先用 `pytest.importorskip` 或 `@pytest.mark.skipif` 包一层，但**必须在 CI 可跑路径**上提供一种方式：推荐后续 Task 加 `tests/conftest.py` 用 `DATABASE_URL` 建 session）：

最小可跑版本——只测「纯函数拼接」：

```python
from app.services.user_body_context import format_user_body_context
from app.models.user import User


def test_format_user_body_context_unchanged() -> None:
    u = User(
        id=1,
        username="t",
        email=None,
        hashed_password="x",
        is_active=True,
        nickname=None,
        avatar_url=None,
        height=170.0,
        weight=65.0,
        age=30,
        gender="male",
    )
    s = format_user_body_context(u)
    assert "170" in s and "65" in s
```

Run: `pytest tests/test_user_preference_service.py -v` — 文件可先只含此测试，**随后**添加 `format_user_context_for_model` 测试。

添加异步测试（需要 `pytest-asyncio` 与真实 DB 时）：

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import user_preference_service
from app.services.user_body_context import format_user_context_for_model


@pytest.mark.asyncio
async def test_format_user_context_includes_preferences(db_session: AsyncSession) -> None:
    # 假设 conftest 提供 db_session 与测试用户
    ...
```

若 Step 1 尚未有 `db_session`，则本步只合入 `format_user_context_for_model` 的**同步**单元测试：mock `list_raw_texts_for_user` 的返回值（通过 `monkeypatch` 注入模块级函数）。

**推荐最小实现：** 在 `user_body_context.py` 增加：

```python
async def format_user_context_for_model(db, user: User) -> str:
    from app.services import user_preference_service

    body = format_user_body_context(user)
    lines = await user_preference_service.list_raw_texts_for_user(db, user.id)
    if not lines:
        return body + "\n\n【饮食偏好与忌口】\n（无）"
    pref = "\n".join(f"- {t}" for t in lines)
    return body + "\n\n【饮食偏好与忌口】\n" + pref
```

`user_preference_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_preference import UserPreference


async def add_preferences(
    db: AsyncSession,
    user_id: int,
    items: list[tuple[str, str]],
) -> None:
    """items: (category, raw_text)"""
    for category, raw_text in items:
        db.add(UserPreference(user_id=user_id, category=category, raw_text=raw_text))
    await db.commit()


async def list_raw_texts_for_user(db: AsyncSession, user_id: int, limit: int = 50) -> list[str]:
    result = await db.execute(
        select(UserPreference.raw_text)
        .where(UserPreference.user_id == user_id)
        .order_by(UserPreference.id.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]
```

同步测试（monkeypatch）示例：

```python
import pytest
from app.models.user import User
from app.services import user_body_context as ubc


@pytest.mark.asyncio
async def test_format_user_context_uses_pref_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list(db, user_id: int, limit: int = 50):
        return ["不吃香菜"]

    monkeypatch.setattr(
        "app.services.user_preference_service.list_raw_texts_for_user",
        fake_list,
    )
    u = User(
        id=1,
        username="t",
        email=None,
        hashed_password="x",
        is_active=True,
        nickname=None,
        avatar_url=None,
        height=None,
        weight=None,
        age=None,
        gender=None,
    )
    out = await ubc.format_user_context_for_model(None, u)
    assert "不吃香菜" in out
    assert "【饮食偏好与忌口】" in out
```

- [ ] **Step 2: 实现服务与 `format_user_context_for_model`**

按上文添加文件与修改；将 `diet_agent` 中需要身体信息的调用点逐步改为 `format_user_context_for_model`（**Task 7 一并改完也可**，但本 task 至少完成函数与单测）。

- [ ] **Step 3: pytest**

```bash
pytest tests/test_user_preference_service.py -v
```

Expected: **PASS**

- [ ] **Step 4: Commit**

```bash
git add app/services/user_preference_service.py app/services/user_body_context.py tests/test_user_preference_service.py
git commit -m "feat: user preference service and model context formatter"
```

---

## Task 4: 身体与偏好抽取 schema + agent 函数

**Files:**

- Create: `app/schemas/body_patch.py`, `app/schemas/preference_extraction.py`
- Create: `app/prompts/body_metrics_chat.py`, `app/prompts/preference_chat.py`
- Modify: `app/agents/diet_agent.py`, `app/prompts/__init__.py`

- [ ] **Step 1: Pydantic schema**

`BodyMetricsDraft` / `PreferenceExtraction` 建议包含：`flow: Literal["ready","need_clarify"]`、`clarify_message: str`、`patch: BodyMetricsPatch | None`、`items: list[PreferenceItem]` 等，与 `IntakeChatExtraction` 风格一致。

- [ ] **Step 2: `extract_body_metrics_chat` / `extract_preferences_chat`**

照抄 `extract_intake_chat` 模式：`HumanMessage(prompt + context)`，`parse_*_json` 用 `model_validate`。

- [ ] **Step 3: 单元测试（mock LLM）**

对 `parse_*_json` 或 `normalize_*` 写固定 JSON 字符串测试，不调用真实 API。

```python
from app.agents.diet_agent import parse_body_metrics_json  # 若你拆出该函数


def test_parse_body_metrics_ready():
    raw = '{"flow":"ready","clarify_message":"","patch":{"height":175.0,"weight":70.0}}'
    ...
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: body metrics and preference extraction prompts and parsers"
```

---

## Task 5: LangGraph 状态与图骨架

**Files:**

- Create: `app/graphs/diet_chat_state.py`
- Create: `app/graphs/diet_chat_graph.py`（第一版：START → `noop` → END + MemorySaver）
- Create: `tests/test_diet_chat_graph_smoke.py`

- [ ] **Step 1: 状态定义**

`DietChatState` 至少包含：`messages`（可选）、`user_id`、`session_id`、`last_user_text`、`route_intent`（可选 str）、`hitl_phase`（`idle`|`awaiting_confirm`）、`pending_confirm_kind`（`none`|`intake`|`burn`|`body`|`preference`）、`reply`（str）、以及各草案字段（可嵌套小 TypedDict）。

使用 `typing_extensions.TypedDict` + `total=False` 处理可选键，或 `Annotated` + `operator.add` 若用 reducer（与 LangGraph 文档一致）。

- [ ] **Step 2: 冒烟测试**

```python
import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.graphs.diet_chat_graph import build_diet_chat_graph


@pytest.mark.asyncio
async def test_graph_compiles_and_runs_noop() -> None:
    g = build_diet_chat_graph().compile(checkpointer=MemorySaver())
    out = await g.ainvoke(
        {"user_id": 1, "session_id": "s", "last_user_text": "hi", "hitl_phase": "idle"},
        config={"configurable": {"thread_id": "1:s"}},
    )
    assert "reply" in out
```

第一版 `noop` 节点可设置 `reply: "ok"`。

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: scaffold diet chat LangGraph state and compiled graph"
```

---

## Task 6: 迁入业务节点（摄入/消耗/闲聊/新意图）与 HITL

**Files:**

- Modify: `app/graphs/diet_chat_graph.py`
- Modify: `app/services/chat_graph_runner.py`（新建若 Task 5 未建）

实现要点（与 spec 第三节一致）：

1. **`ingest_message`**：写入 `last_user_text`；若从 `interrupt` 恢复，LangGraph 会把 resume 值注入——用 `Command(resume=...)` 或在 state 中携带 `resume_decision`（按你所选 LangGraph 版本 API 编写，**以官方 human-in-the-loop 文档为准**）。
2. **`route_intent`**：调用 `route_chat_intent(route_ctx)`；失败时 `ChatIntentRoute(intent=log_intake)`。
3. **条件边**：`hitl_phase == awaiting_confirm` → `hitl_resume`。
4. **子图或节点函数**：`run_intake_flow`、`run_burn_flow`、`run_general`、`run_body_flow`、`run_preference_flow`，内部复用 `agent_service` 中已有辅助函数（将 `_build_confirm_preview`、`_parse_confirm_intent` 抽到 `app/services/chat_confirm_utils.py` 以降低循环导入，**推荐**）。
5. **`present_confirm` + `interrupt`**：在草案齐全后设置 `reply` 为预览文本，调用 `interrupt({"kind": pending_confirm_kind})`。
6. **`hitl_resume`**：解析用户文本 → confirm 则调用 commit 节点（传入 `AsyncSession` 通过 `configurable` 或 closure）。

**数据库 session 注入 LangGraph：** 使用 `config["configurable"]["db"]` 传入 `AsyncSession`，或在 `run_chat_turn` 内在每个 commit 节点用新 session（推荐与 FastAPI 请求同生命周期：在 `run_chat_turn` 里 `async with session_factory()` 包一层，**文档化**选择）。

- [ ] **Step 1: 抽取 `_parse_confirm_intent` 到公共模块**

Create `app/services/chat_confirm_utils.py`，从 `agent_service.py` 剪切 `_parse_confirm_intent` 及常量，`agent_service` 与新图均引用。

- [ ] **Step 2: 集成测试（MemorySaver）**

`tests/test_diet_chat_graph_hitl.py`：mock `route_chat_intent` 返回 `update_preferences`，mock 抽取返回 `ready` + 一条偏好，`interrupt` 后第二次 `ainvoke` 带 `Command(resume="confirm")`（或等价），断言 `add_preferences` 被调用（`unittest.mock.AsyncMock`）。

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: diet chat graph nodes, HITL interrupt, and confirm resume"
```

---

## Task 7: `chat_graph_runner` 与 `agent_service` 切流

**Files:**

- Create: `app/services/chat_graph_runner.py`
- Modify: `app/services/agent_service.py`
- Modify: `app/core/config.py`

- [ ] **Step 1: Config**

```python
USE_LANGGRAPH_CHAT: bool = False
```

- [ ] **Step 2: `run_chat_turn`**

签名示例：

```python
async def run_chat_turn(
    payload: ChatIn,
    db: AsyncSession,
    user: User,
) -> ChatOut:
    ...
```

内部：`thread_id = f"{user.id}:{_session_id(payload)}"`，`graph.ainvoke(..., config={"configurable": {"thread_id": thread_id, "db": db}})`。

- [ ] **Step 3: `agent_service.chat` 分支**

```python
from app.core.config import settings

async def chat(...):
    if settings.USE_LANGGRAPH_CHAT:
        from app.services.chat_graph_runner import run_chat_turn
        return await run_chat_turn(payload, db, user)
    ...  # 现有实现
```

- [ ] **Step 4: 将 `extract_intake_chat` / `generate_general_advice` 的 user 上下文改为 `format_user_context_for_model`**

在图节点中传入 db 与 user，替换原 `format_user_body_context(user)` 调用点（与 spec 一致）。

- [ ] **Step 5: 手工验证**

```bash
uv run uvicorn app.main:app --reload
```

`.env` 设 `USE_LANGGRAPH_CHAT=true`，对 `/api/v1/agent/chat` 测摄入确认与偏好确认各一轮。

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: wire chat graph runner and feature flag"
```

---

## Task 8: 清理与退役 `chat_pending_service`（可选第二阶段）

**Files:**

- Modify: `app/services/chat_pending_service.py`（文档标注 deprecated）
- Modify: `app/services/agent_service.py`（flag 为真时不再调用 pending）

仅在 `USE_LANGGRAPH_CHAT=true` 稳定后执行；spec 允许短期双轨。**本 task 可单独 PR。**

- [ ] **Step 1: 文档** 在 `chat_pending_service.py` 模块 docstring 说明仅旧路径使用。

- [ ] **Step 2: Commit** `docs: deprecate chat_pending_service when LangGraph enabled`

---

## Task 9: 生产级 Checkpointer（可选）

**Files:**

- Modify: `pyproject.toml`
- Modify: `app/services/chat_graph_runner.py`

若使用 Redis：增加依赖 `langgraph-checkpoint-redis`（版本与 `langgraph` 发行说明对齐），用 `AsyncRedisSaver.from_conn_string(settings.REDIS_URL)` 替换 `MemorySaver`（注意 **async** 连接生命周期）。

- [ ] **Step 1: 阅读** https://langchain-ai.github.io/langgraph/concepts/persistence/ 与 Redis saver 小节。

- [ ] **Step 2: 配置** `LANGGRAPH_CHECKPOINTER=memory|redis`，默认 `memory`。

- [ ] **Step 3: Commit** `feat: configurable LangGraph checkpointer`

---

## Plan self-review

| Spec 条款 | 对应 Task |
|-----------|-----------|
| Supervisor + 子图 + HITL | Task 5–6 |
| `user_preference` 表 | Task 1 |
| 身体数据同源 `users` | Task 6 commit 调 `user_service.update_user` |
| 设置页不展示偏好 | 无前端任务；REST 不暴露列表即可 |
| 路由扩展意图 | Task 2 |
| `format_user_context_for_model` | Task 3、7 |
| 错误降级（路由失败→log_intake 等） | Task 6 `route_intent` 节点 |
| 测试 | 各 Task 内 |

**Placeholder scan:** 无 TBD；迁移 revision id 用 `<new_id>` 处已说明以 `alembic revision` 生成为准。

**Type consistency:** `ChatRouteIntent` 字符串与 `route_chat_intent` JSON、`parse_intent_route_json` 必须一致；`pending_confirm_kind` 与 commit 分支枚举一致。

---

## Execution handoff

**计划已保存至** `docs/superpowers/plans/2026-04-24-langgraph-agent-hitl.md`。

**执行方式二选一：**

1. **Subagent-Driven（推荐）** — 每个 Task 单独开 subagent，任务间人工过一遍 diff。  
2. **Inline Execution** — 本会话用 `executing-plans` 按 Task 连续实现，大块处设检查点。

你要用哪一种？
