# Banner 生图链路上下文日志实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `generate_image_and_upload` 三阶段（Ark 请求、图片下载、OSS 上传）增加分阶段 `loguru` 日志；在 `generate_cards` 中对「有 `image_prompt` 但无 `image_url`」打汇总 `warning`；保持函数仍返回 `str | None`。

**Architecture:** 在 `app/agents/banner_agent.py` 内按阶段拆分 try/except，失败时 `logger.exception`，消息使用统一前缀 `banner_image:` + 阶段名（`ark_request` / `image_fetch` / `oss_upload`）。`image_prompt` 仅写入截断片段（80 字符，超出加 `…`）。OSS 阶段额外记录 `settings.OSS_BUCKET` 与 `settings.OSS_ENDPOINT`。`banner_service` 在写入 `ready` 前若 `image_prompt` 非空且 `image_url` 为 `None` 则 `logger.warning`。

**Tech Stack:** Python 3.12、httpx、loguru、pytest、pytest-asyncio、`unittest.mock`。

**依据规范:** `docs/superpowers/specs/2026-04-23-banner-image-pipeline-observability-design.md`

---

## 文件映射

| 文件 | 职责 |
|------|------|
| `app/agents/banner_agent.py` | 分阶段日志、`generate_image_and_upload` 重构 |
| `app/services/banner_service.py` | `generate_cards` 内汇总 `warning` |
| `test/test_banner_service.py` | 新增/扩展单测（mock httpx、OSS、logger） |

---

### Task 1: `generate_image_and_upload` — OSS 失败单测

**Files:**
- Modify: `test/test_banner_service.py`

- [ ] **Step 1: 编写失败用例（OSS 抛错）**

在 `test/test_banner_service.py` 末尾增加：

```python
@pytest.mark.asyncio
async def test_generate_image_and_upload_logs_oss_stage_on_upload_failure():
    from app.agents import banner_agent

    mock_post_resp = MagicMock()
    mock_post_resp.raise_for_status = MagicMock()
    mock_post_resp.json.return_value = {"data": [{"url": "https://cdn.example.com/out.png"}]}

    mock_get_resp = MagicMock()
    mock_get_resp.raise_for_status = MagicMock()
    mock_get_resp.content = b"\xff\xd8\xff fake jpeg"

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_post_resp)
    mock_client.get = AsyncMock(return_value=mock_get_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch.object(banner_agent.httpx, "AsyncClient", return_value=mock_cm), \
         patch.object(banner_agent, "upload_banner_image", side_effect=RuntimeError("oss put failed")), \
         patch.object(banner_agent, "logger") as mock_logger:
        out = await banner_agent.generate_image_and_upload("a sunny breakfast plate")

    assert out is None
    mock_logger.exception.assert_called_once()
    fmt, _kwargs = mock_logger.exception.call_args[0][0], mock_logger.exception.call_args[1]
    assert "banner_image:oss_upload" in fmt
```

说明：`loguru` 默认不走标准库 `logging`，因此用 `patch.object(banner_agent, "logger")` 断言 `exception` 被调用，而不是 `caplog`。

- [ ] **Step 2: 运行测试确认失败**

运行：

```bash
cd D:\AgentDemo\dietAgent_demo1
pytest test/test_banner_service.py::test_generate_image_and_upload_logs_oss_stage_on_upload_failure -v
```

预期：**失败**（例如仍为一整块 `try/except` 吞掉或未调用 `logger.exception`）。

- [ ] **Step 3: Commit**

```bash
git add test/test_banner_service.py
git commit -m "test: expect staged logging when banner OSS upload fails"
```

---

### Task 2: 实现 `banner_agent.generate_image_and_upload` 分阶段日志

**Files:**
- Modify: `app/agents/banner_agent.py`

- [ ] **Step 1: 实现辅助函数与分阶段逻辑**

在 `app/agents/banner_agent.py` 中：

1. 增加：`from loguru import logger`
2. 在模块级增加截断辅助（示例实现，可按项目风格微调）：

```python
def _prompt_snippet(image_prompt: str, max_len: int = 80) -> str:
    s = (image_prompt or "").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"
```

3. 将 `generate_image_and_upload` 替换为：保留 `async with httpx.AsyncClient(timeout=60.0) as client:` 外层；在内部分三段：
   - **ark_request:** `post` + `raise_for_status`；再安全解析 `resp.json()` 取 `data[0]["url"]`。`HTTPStatusError` 与其它异常、`KeyError`/`IndexError`/`JSON` 解析问题分别或合并用 `logger.exception`，消息格式串内含 `banner_image:ark_request`，参数含 `_prompt_snippet(image_prompt)`，**不要**记录 Authorization。
   - **image_fetch:** `get(image_url, timeout=30.0)` + `raise_for_status`。异常时 `logger.exception`，格式串含 `banner_image:image_fetch`，可记录截断后的 URL（例如 `image_url[:100]` 若长度大于 100 则加提示）与 `prompt` snippet。
   - **oss_upload:** `upload_banner_image(img_resp.content)` 包在 try/except，失败时 `logger.exception`，格式串含 `banner_image:oss_upload`，参数包含 `settings.OSS_BUCKET`、`settings.OSS_ENDPOINT`、`_prompt_snippet(image_prompt)`。

任一段失败返回 `None`；全部成功返回 OSS 公网 URL 字符串。

- [ ] **Step 2: 运行 Task 1 单测**

```bash
pytest test/test_banner_service.py::test_generate_image_and_upload_logs_oss_stage_on_upload_failure -v
```

预期：**通过**。

- [ ] **Step 3: Commit**

```bash
git add app/agents/banner_agent.py
git commit -m "feat(banner): add staged logging for image generation and OSS upload"
```

---

### Task 3: Ark 请求失败单测（可选，覆盖规范「可选」）

**Files:**
- Modify: `test/test_banner_service.py`

- [ ] **Step 1: 新增用例 `post` 返回 401**

```python
@pytest.mark.asyncio
async def test_generate_image_and_upload_logs_ark_stage_on_http_error():
    from app.agents import banner_agent
    import httpx

    mock_post_resp = MagicMock()
    mock_post_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=MagicMock()
    )

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_post_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch.object(banner_agent.httpx, "AsyncClient", return_value=mock_cm), \
         patch.object(banner_agent, "logger") as mock_logger:
        out = await banner_agent.generate_image_and_upload("prompt")

    assert out is None
    mock_logger.exception.assert_called_once()
    assert "banner_image:ark_request" in mock_logger.exception.call_args[0][0]
```

- [ ] **Step 2: 运行测试**

```bash
pytest test/test_banner_service.py::test_generate_image_and_upload_logs_ark_stage_on_http_error -v
```

预期：**通过**。

- [ ] **Step 3: Commit**

```bash
git add test/test_banner_service.py
git commit -m "test(banner): cover ark_request failure logging"
```

---

### Task 4: `banner_service.generate_cards` 汇总 warning

**Files:**
- Modify: `app/services/banner_service.py`
- Modify: `test/test_banner_service.py`

- [ ] **Step 1: 编写失败用例（汇总 warning）**

在 `test/test_banner_service.py` 增加。`generate_cards` 依次 `await db.execute`：用户查询、`_get_last7_intake`、`_get_last7_burn`、`_red_cut_titles`（共 4 次）。Patch `banner_service.rag_service.retrieve`（不是 `banner_service.retrieve`）。`format_user_body_context` 需要 `user.height/weight/age/gender` 显式为 `None`，避免未配置属性的 `MagicMock` 在格式化时出错。

```python
@pytest.mark.asyncio
async def test_generate_cards_warns_when_image_missing_despite_prompt():
    from app.services import banner_service

    user = MagicMock()
    user.id = 42
    user.height = None
    user.weight = None
    user.age = None
    user.gender = None

    def result_scalar_one(u):
        r = MagicMock()
        r.scalar_one_or_none.return_value = u
        return r

    def result_empty_logs():
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            result_scalar_one(user),
            result_empty_logs(),
            result_empty_logs(),
            result_empty_logs(),
        ]
    )

    async def refresh_sets_id(card):
        card.id = "card-uuid-1"

    mock_db.refresh = AsyncMock(side_effect=refresh_sets_id)
    mock_db.commit = AsyncMock()

    with patch.object(banner_service.rag_service, "retrieve", new_callable=AsyncMock, return_value=[]), \
         patch.object(banner_service, "generate_card_drafts", new_callable=AsyncMock) as mock_drafts, \
         patch.object(banner_service, "generate_image_and_upload", new_callable=AsyncMock) as mock_img, \
         patch.object(banner_service, "logger") as mock_logger:
        mock_drafts.return_value = [
            {"title": "t", "desc": "d", "image_prompt": "breakfast scene", "category": "diet"},
        ]
        mock_img.return_value = None

        await banner_service.generate_cards(user_id=42, count=1, db=mock_db)

    mock_logger.warning.assert_called()
    joined = " ".join(str(a) for c in mock_logger.warning.call_args_list for a in c[0])
    assert "42" in joined
    assert "card-uuid-1" in joined
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest test/test_banner_service.py::test_generate_cards_warns_when_image_missing_despite_prompt -v
```

预期：**失败**（尚未加 `warning`）。

- [ ] **Step 3: 在 `generate_cards` 中写入 warning**

在 `app/services/banner_service.py` 中，在 `image_url = await generate_image_and_upload(...)` 之后、`card.image_url = image_url` 之前或之后增加：

```python
        if card.image_prompt and image_url is None:
            logger.warning(
                "Banner card ready without image user_id={} card_id={} (see banner_image:* logs)",
                user_id,
                card.id,
            )
```

- [ ] **Step 4: 运行测试与全量 banner 测试**

```bash
pytest test/test_banner_service.py -v
```

预期：全部通过。

- [ ] **Step 5: Commit**

```bash
git add app/services/banner_service.py test/test_banner_service.py
git commit -m "feat(banner): warn when card has prompt but no image_url"
```

---

### Task 5: 全量回归与手工验证说明

- [ ] **Step 1: 运行项目测试**

```bash
pytest test/ -q
```

预期：无新增失败。

- [ ] **Step 2: 手工验证（本地）**

临时将 `OSS_ACCESS_KEY_SECRET` 设为错误值或通过环境变量覆盖，触发一次 `ensure_pool` / 卡片生成，确认日志中出现 `banner_image:oss_upload` 及异常堆栈。

- [ ] **Step 3: Commit（仅当有文档或配置补充时）**

若无额外文件变更，可跳过。

---

## 计划自检

**规范覆盖:** 三阶段命名与前缀、`loguru`、prompt 截断、OSS bucket/endpoint、`banner_service` warning、单测 OSS 与可选 Ark、手工验证 — 均已落入 Task 1–5。

**占位符:** 无 TBD；Task 4 已给出与当前 `generate_cards` 一致的 4 次 `execute` `side_effect`。

**类型一致:** `generate_image_and_upload` 签名不变；`logger` 均为 `loguru`。

---

## 执行方式（完成后由执行者选择）

计划保存于 `docs/superpowers/plans/2026-04-23-banner-image-pipeline-observability.md`。

1. **Subagent-Driven（推荐）** — 每任务独立子代理，任务间评审。  
2. **Inline Execution** — 本会话按任务批量执行，`executing-plans` 检查点。

请选择其一后再开始改代码。
