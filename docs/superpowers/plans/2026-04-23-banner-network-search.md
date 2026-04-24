# Banner 联网（enable_search）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `generate_card_drafts` 中，当 `BANNER_ENABLE_NETWORK_SEARCH=True` 时，经 LangChain `ChatOpenAI` 向 DashScope 兼容接口透传 `extra_body={"enable_search": True}`；失败时**最多再试一次**且关闭联网；`generate_cards` 传入 `user_id` 供日志；提示词增加联网安全与优先级说明。默认不联网，与现状一致。

**Architecture:** 在 `app/agents/banner_agent.py` 中新增 **非缓存** 工厂 ` _get_llm_for_banner(*, enable_search: bool) -> ChatOpenAI`，与 `diet_agent._get_llm` 解耦，复用 `settings` 的 `QWEN_MODEL` / `DASHSCOPE_*` / `temperature=0.2`。**不**用 `@lru_cache` 缓存带不同 `extra_body` 的客户端。官方约定（阿里云百炼 / OpenAI 兼容）：联网参数放在 **`extra_body`**，与 LangChain 文档一致；**不要**用 `model_kwargs` 传 `enable_search`（非 OpenAI 标准参数易报错）。依据文档：`https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope` 中 `enable_search` 与 `extra_body` 说明。

**Tech Stack:** Python 3.12、FastAPI、`langchain-openai` `ChatOpenAI`、`pydantic-settings`、pytest、`unittest.mock`、loguru。

**依据规范:** `docs/superpowers/specs/2026-04-23-banner-network-search-design.md`

---

## 文件映射

| 文件 | 职责 |
|------|------|
| `app/core/config.py` | 新增 `BANNER_ENABLE_NETWORK_SEARCH: bool = False` |
| `app/agents/banner_agent.py` | `_get_llm_for_banner`；`generate_card_drafts` 使用联网开关 + 降级重试；可选 `user_id` 参数；**移除**对 `diet_agent._get_llm` 的依赖（改为本文件内工厂，避免误用 diet 的 LLM 单例） |
| `app/services/banner_service.py` | `generate_cards` 内调用 `generate_card_drafts(..., user_id=user_id)` |
| `app/prompts/banner_content.py` | 扩展 `BANNER_CONTENT_SYSTEM` 与/或 `format_banner_content_prompt` 中任务段：联网为辅助、优先指南与摘要、禁止医疗诊断与疗效承诺、冲突时以 RAG/摘要为准 |
| `test/test_banner_service.py` | 更新已有 `test_generate_card_drafts_returns_list` 的 patch 目标；新增断言 `extra_body` 的用例 |

---

### Task 1: 配置项 `BANNER_ENABLE_NETWORK_SEARCH`

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: 在 `Settings` 中增加字段**

在 `BANNER_REDCUT_CLEANUP_BATCH_SIZE` 附近（或 `BANNER_GET_DAILY_LIMIT` 成组处）增加：

```python
BANNER_ENABLE_NETWORK_SEARCH: bool = False
```

说明：默认 `False` 与 spec 一致，避免未显式配置即产生联网费用；生产在 `.env` 设 `BANNER_ENABLE_NETWORK_SEARCH=true` 时打开。

- [ ] **Step 2: Commit**

```bash
cd D:\AgentDemo\dietAgent_demo1
git add app/core/config.py
git commit -m "feat(config): BANNER_ENABLE_NETWORK_SEARCH for banner LLM"
```

---

### Task 2: `banner_agent` 工厂 + `generate_card_drafts` 行为

**Files:**
- Modify: `app/agents/banner_agent.py`

- [ ] **Step 1: 调整 import 与增加工厂函数**

- 在文件顶部将 `from app.agents.diet_agent import _get_llm` **删除**。
- 增加：

```python
from functools import lru_cache

from langchain_openai import ChatOpenAI
```

- 在 `_strip_json` 之前或之后增加（**不要**对 banner LLM 使用 `@lru_cache`，避免 `extra_body` 被错误复用；此处仅为与 `diet_agent` 同构的温度，不缓存多版本）：

```python
def _get_llm_for_banner(*, enable_search: bool) -> ChatOpenAI:
    extra = {"enable_search": True} if enable_search else None
    return ChatOpenAI(
        model=settings.QWEN_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.DASHSCOPE_BASE_URL,
        temperature=0.2,
        extra_body=extra,
    )
```

若 `ChatOpenAI` 在你们的 `langchain-openai` 版本不接受 `extra_body=None`，则改为 `extra_body=extra or {}` 或 `extra_body=extra if extra is not None else {}`，以「关闭联网时请求体**不含** `enable_search`」为准（对空 `extra_body` 做一次与 DashScope 的实调或单测确认无多余字段问题）。

- [ ] **Step 2: 为 `generate_card_drafts` 增加 `user_id` 与重试逻辑**

将 `generate_card_drafts` 签名改为含可选 `user_id: int | None = None`（放在 `count: int` 之后）。

在函数体内（保留原有 `format_banner_content_prompt` 与 `messages` 构建），用下面逻辑**替换**原先单次 `_get_llm()` + `ainvove` 块（伪代码结构固定，照抄时与现有 `SystemMessage`/`HumanMessage` 内容保持一致）：

```python
    messages = [
        SystemMessage(content=BANNER_CONTENT_SYSTEM),
        HumanMessage(content=prompt),
    ]
    use_net = bool(settings.BANNER_ENABLE_NETWORK_SEARCH)

    if use_net:
        try:
            llm = _get_llm_for_banner(enable_search=True)
            resp = await llm.ainvoke(messages)
        except Exception as e:
            logger.warning(
                "banner: card draft with enable_search failed user_id={} err={!r}",
                user_id,
                e,
            )
            llm = _get_llm_for_banner(enable_search=False)
            resp = await llm.ainvoke(messages)
    else:
        llm = _get_llm_for_banner(enable_search=False)
        resp = await llm.ainvoke(messages)
```

- 后续 `content` 解析、`_strip_json`、`json.loads`、列表归一与 `return data[:count]` **与现实现保持一致**（勿改 JSON 契约）。

- [ ] **Step 3: Commit**

```bash
git add app/agents/banner_agent.py
git commit -m "feat(banner): DashScope enable_search via extra_body with offline fallback"
```

---

### Task 3: `banner_service.generate_cards` 传入 `user_id`

**Files:**
- Modify: `app/services/banner_service.py`

- [ ] **Step 1: 更新 `generate_card_drafts` 调用**

将：

```python
        drafts = await generate_card_drafts(
            guideline_chunks=chunks,
            user_body_block=format_user_body_context(user),
            intake_summary=_intake_summary(intake_logs),
            burn_summary=_burn_summary(burn_logs),
            red_cut_titles=red_cut,
            count=count,
        )
```

改为增加 `user_id=user_id` 关键字实参（`user_id` 为当前函数参数）。

- [ ] **Step 2: Commit**

```bash
git add app/services/banner_service.py
git commit -m "feat(banner): pass user_id into generate_card_drafts for logs"
```

---

### Task 4: 提示词（联网与合规）

**Files:**
- Modify: `app/prompts/banner_content.py`

- [ ] **Step 1: 扩展 `BANNER_CONTENT_SYSTEM`**

在短系统字符串末尾拼接一段（可合并为一条长字符串，保持风格与现有引号方式一致）：

- 可联网时：互联网信息**仅作补充**；**优先**「膳食指南参考」与「用户身体/近7天记录/已拒绝主题」；表述为**科普、个体化建议**。
- 禁止将网页或模型输出作为**疾病诊断、疗效承诺、替代就医**；有冲突时以**所给指南与记录**为准、保守表述。

注意：不引入 markdown 与 JSON 外内容的要求**保持不变**（系统仍说「只输出 JSON」如现有）。

- [ ] **Step 2: Commit**

```bash
git add app/prompts/banner_content.py
git commit -m "docs(prompt): banner 联网安全与信源优先级"
```

---

### Task 5: 单测 — 复用与新增

**Files:**
- Modify: `test/test_banner_service.py`

- [ ] **Step 1: 修改 `test_generate_card_drafts_returns_list` 的 mock**

- 将 `patch("app.agents.banner_agent._get_llm")` 改为 `patch("app.agents.banner_agent._get_llm_for_banner")`；`return_value=mock_llm` 等不变。测试环境默认未打开 `BANNER_ENABLE_NETWORK_SEARCH` 时应只走关闭联网分支，在断言处增加一次：

```python
        mock_get_llm.assert_called_once_with(enable_search=False)
```

（`mock_get_llm` 与 `patch` 的 `as` 变量名一致即可。）

- [ ] **Step 2: 新增用例 `test_generate_card_drafts_calls_enable_search_true_when_config_on`**

在**同一文件**追加：

```python
@pytest.mark.asyncio
async def test_generate_card_drafts_calls_enable_search_true_when_config_on():
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='[{"title":"T","desc":"D","image_prompt":"P","category":"diet"}]'
        )
    )
    with patch("app.agents.banner_agent._get_llm_for_banner") as mock_get:
        mock_get.return_value = mock_llm
        with patch("app.agents.banner_agent.settings") as s:
            s.BANNER_ENABLE_NETWORK_SEARCH = True
            from app.agents.banner_agent import generate_card_drafts

            out = await generate_card_drafts(
                guideline_chunks=[],
                user_body_block="b",
                intake_summary="i",
                burn_summary="b2",
                red_cut_titles=[],
                count=1,
            )
    assert len(out) == 1
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs.get("enable_search") is True
```

（成功路径下只调用一次 ` _get_llm_for_banner` 且为 `True`；若你后续把「仅失败再关联网」的 except 也打成日志并二次调用，本用例在「首次即成功」时仍只应**一次** `True`。）

- [ ] **Step 3: 运行全量与 banner 相关测试**

```bash
cd D:\AgentDemo\dietAgent_demo1
pytest test/test_banner_service.py -v
```

预期：全部通过。

- [ ] **Step 4: Commit**

```bash
git add test/test_banner_service.py
git commit -m "test(banner): mock _get_llm_for_banner and assert enable_search path"
```

---

## 规范自检（计划 vs spec）

| Spec 要求 | 计划任务 |
|-----------|----------|
| `BANNER_ENABLE_NETWORK_SEARCH` 默认 False | Task 1 |
| 仅 Banner 链路透传、专用工厂、不影响 diet | Task 2（独立 `_get_llm_for_banner`，移除 `_get_llm` import） |
| `extra_body` / 官方 `enable_search` | Task 2 代码块（阿里云：Python `extra_body`） |
| 失败重试、第二次关联网 + 日志含 user_id | Task 2 + Task 3 |
| 提示词安全与优先级 | Task 4 |
| 单测不连外网、断言联网参数 | Task 5 |

**占位符检查：** 本计划无 “TBD / 稍后” 等空话。若 `patch("app.agents.banner_agent.settings")` 在实现时与 Pydantic `Settings` 冲突，可改为对 `BANNER_ENABLE_NETWORK_SEARCH` 做 `patch` 目标路径的等价物（以实际代码为准）。

---

**Plan complete and saved to** `docs/superpowers/plans/2026-04-23-banner-network-search.md`。**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 用新子代理执行，任务间做简短评审，迭代快。  
2. **Inline execution** — 在本会话中按 `executing-plans` 连续执行任务并设检查点。

你更倾向哪一种？
