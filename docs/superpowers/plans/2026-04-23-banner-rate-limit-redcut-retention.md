# Banner GET 日配额与红切清理实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `GET /api/v1/banners` 增加东八区自然日每用户 20 次配额；将生成提示词中的红切标题限制为最近 10 条；对满 7 天的红切记录定时清理（先尝试删 OSS，**无论 OSS 是否成功都删 DB**）。

**Architecture:** 配额用 PostgreSQL 表 `banner_daily_get_quota` + `INSERT … ON CONFLICT DO UPDATE … WHERE request_count < limit` 原子递增；东八区日期复用 `app/db/local_day.py`（`INSIGHT_TZ` / `today_local`）。红切清理在 FastAPI `lifespan` 中启动 `asyncio` 后台循环，按可配置间隔调用 `banner_service` 批处理；OSS 删除在 `oss_service` 中按 `image_url` 与 `OSS_BASE_URL` 解析 key，同步 SDK 用 `asyncio.to_thread` 包裹以免阻塞事件循环。

**Tech Stack:** FastAPI、SQLAlchemy 2 async、PostgreSQL、Alembic、oss2、loguru、pytest / pytest-asyncio。

**规格来源:** [../specs/2026-04-23-banner-rate-limit-redcut-retention-design.md](../specs/2026-04-23-banner-rate-limit-redcut-retention-design.md)

---

## 文件一览

| 文件 | 职责 |
|------|------|
| `app/models/banner_daily_get_quota.py` | 配额 ORM 模型 |
| `alembic/versions/<new>_add_banner_daily_get_quota.py` | 建表 + 可选清理索引 |
| `app/core/config.py` | `BANNER_GET_DAILY_LIMIT`、`BANNER_REDCUT_RETENTION_DAYS`、`BANNER_REDCUT_CLEANUP_INTERVAL_SECONDS`、`BANNER_REDCUT_CLEANUP_BATCH_SIZE` |
| `.env.example` | 上述变量示例 |
| `app/core/error_code.py` | `BANNER_GET_RATE_LIMITED` 与文案 |
| `app/db/local_day.py` | `next_shanghai_midnight_after(today: date) -> datetime`（`tzinfo=Asia/Shanghai`） |
| `app/services/oss_service.py` | `delete_banner_object_by_url(url: str \| None) -> None` |
| `app/services/banner_service.py` | `consume_banner_get_quota`、`cleanup_expired_red_cut_cards`；`_red_cut_titles` 改排序 + limit 10 |
| `app/api/v1/banner.py` | `get_banners` 开头调用 `consume_banner_get_quota` |
| `app/main.py` | `lifespan` 内启动/取消清理后台任务 |
| `tests/test_banner_quota_and_redcut.py` | 纯函数 + mock async session 的配额逻辑测试 |

---

### Task 1: 东八区「次日 0 点」辅助函数与单元测试

**Files:**
- Create: `tests/test_banner_quota_and_redcut.py`（本任务只写第一个测试）
- Modify: `app/db/local_day.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_banner_quota_and_redcut.py`：

```python
from datetime import date, datetime

from zoneinfo import ZoneInfo

from app.db.local_day import INSIGHT_TZ, next_shanghai_midnight_after


def test_next_shanghai_midnight_after() -> None:
    d = date(2026, 4, 23)
    mid = next_shanghai_midnight_after(d)
    assert mid.tzinfo == INSIGHT_TZ
    assert mid == datetime(2026, 4, 24, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
```

- [ ] **Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_banner_quota_and_redcut.py::test_next_shanghai_midnight_after -v`

预期: `ImportError` 或 `AttributeError`（函数不存在）

- [ ] **Step 3: 最小实现**

在 `app/db/local_day.py` 末尾增加：

```python
def next_shanghai_midnight_after(today: date) -> datetime:
    """东八区日历日 `today` 的次日 00:00（用于配额重置展示）。"""
    next_day = today + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=INSIGHT_TZ)
```

确认文件顶部已有 `timedelta`、`time`、`datetime`、`date` 导入（已有 `datetime, time, timedelta, date`）。

- [ ] **Step 4: 运行测试通过**

运行: `python -m pytest tests/test_banner_quota_and_redcut.py::test_next_shanghai_midnight_after -v`

预期: PASS

- [ ] **Step 5: Commit**

```bash
git add app/db/local_day.py tests/test_banner_quota_and_redcut.py
git commit -m "feat: next Shanghai midnight helper for banner quota"
```

---

### Task 2: 配置项

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: 在 `Settings` 中增加字段**

```python
    BANNER_GET_DAILY_LIMIT: int = 20
    BANNER_REDCUT_RETENTION_DAYS: int = 7
    BANNER_REDCUT_CLEANUP_INTERVAL_SECONDS: int = 3600
    BANNER_REDCUT_CLEANUP_BATCH_SIZE: int = 500
```

- [ ] **Step 2: `.env.example` 追加注释行**

```env
# Banner：GET 日配额（东八区自然日）、红切保留天数、清理任务间隔与批量
# BANNER_GET_DAILY_LIMIT=20
# BANNER_REDCUT_RETENTION_DAYS=7
# BANNER_REDCUT_CLEANUP_INTERVAL_SECONDS=3600
# BANNER_REDCUT_CLEANUP_BATCH_SIZE=500
```

- [ ] **Step 3: Commit**

```bash
git add app/core/config.py .env.example
git commit -m "feat: banner quota and red-cut cleanup settings"
```

---

### Task 3: ErrorCode

**Files:**
- Modify: `app/core/error_code.py`

- [ ] **Step 1: 增加枚举与文案**

在 `ErrorCode` 中 `LOG_NOT_FOUND = 40002` 之后增加：

```python
    BANNER_GET_RATE_LIMITED = 40003
```

在 `ERROR_MESSAGES` 中增加：

```python
    ErrorCode.BANNER_GET_RATE_LIMITED: "今日推荐卡片获取次数已达上限",
```

- [ ] **Step 2: Commit**

```bash
git add app/core/error_code.py
git commit -m "feat: error code for banner GET rate limit"
```

---

### Task 4: 配额表模型与 Alembic 迁移

**Files:**
- Create: `app/models/banner_daily_get_quota.py`
- Create: `alembic/versions/e7f8a9b0c1d2_add_banner_daily_get_quota.py`（文件名与 revision id 若冲突可改为新生成 UUID）
- Modify: `app/models/__init__.py`（若项目通过 `__init__` 收集模型，需导出，否则确保 Alembic `env.py` 能加载到 metadata — 按现有 `recommendation_card` 方式处理）

**迁移 `down_revision`:** 必须指向当前线头 `a8f0c1d2e3b4`（`add_user_insight_summaries`）。

- [ ] **Step 1: 模型 `app/models/banner_daily_get_quota.py`**

```python
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BannerDailyGetQuota(Base):
    __tablename__ = "banner_daily_get_quota"
    __table_args__ = (
        UniqueConstraint("user_id", "quota_date", name="uq_banner_daily_get_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    quota_date: Mapped[date] = mapped_column(Date, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: Alembic `upgrade()`**

创建表 `banner_daily_get_quota`，列与模型一致；`request_count` 默认值 `0`；唯一约束 `uq_banner_daily_get_user_date`；`downgrade()` 删表。

可选（建议）：为清理任务增加部分索引（若与表同迁移或单独迁移均可）：

```python
op.create_index(
    "ix_recommendation_cards_red_cut_cleanup",
    "recommendation_cards",
    ["status", "red_cut_at"],
    postgresql_where=sa.text("status = 'red_cut' AND red_cut_at IS NOT NULL"),
)
```

`downgrade` 时 `drop_index`.

- [ ] **Step 3: 本地执行迁移**

运行: `python -m alembic upgrade head`（在项目 venv 中）

预期: 成功 applied

- [ ] **Step 4: Commit**

```bash
git add app/models/banner_daily_get_quota.py alembic/versions/e7f8a9b0c1d2_add_banner_daily_get_quota.py
git commit -m "feat: banner_daily_get_quota table and migration"
```

---

### Task 5: `consume_banner_get_quota` 与单元测试（mock DB）

**Files:**
- Modify: `app/services/banner_service.py`
- Modify: `tests/test_banner_quota_and_redcut.py`

- [ ] **Step 1: 写失败测试（mock `AsyncSession.execute`）**

在 `tests/test_banner_quota_and_redcut.py` 增加：

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.error_code import ErrorCode
from app.core.exceptions import BusinessException
from app.services import banner_service


@pytest.mark.asyncio
async def test_consume_banner_get_quota_rejects_when_no_returning_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(banner_service, "settings", MagicMock(BANNER_GET_DAILY_LIMIT=20))

    db = AsyncMock()
    # 第一次 RETURNING 空：表示未更新
    exec_result = MagicMock()
    exec_result.first = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=exec_result)

    # SELECT 当前用量
    sel_result = MagicMock()
    sel_result.scalar_one = MagicMock(return_value=20)
    db.execute = AsyncMock(side_effect=[exec_result, sel_result])

    with pytest.raises(BusinessException) as ei:
        await banner_service.consume_banner_get_quota(1, db)
    assert ei.value.code == ErrorCode.BANNER_GET_RATE_LIMITED
```

根据最终实现，`side_effect` 可能需要调整为「两次 execute」的真实顺序；本测试目的是 **先红后修**。

- [ ] **Step 2: 运行测试确认失败**

运行: `python -m pytest tests/test_banner_quota_and_redcut.py::test_consume_banner_get_quota_rejects_when_no_returning_row -v`

预期: 失败（函数不存在或行为不符）

- [ ] **Step 3: 实现 `consume_banner_get_quota`**

在 `app/services/banner_service.py`：

1. 增加导入：`from sqlalchemy.dialects.postgresql import insert`、`from app.models.banner_daily_get_quota import BannerDailyGetQuota`、`from app.db.local_day import next_shanghai_midnight_after, today_local`、`from app.core.config import settings`、`from app.core.exceptions import BusinessException`、`from app.core.error_code import ErrorCode`。

2. 实现函数（核心逻辑；`limit` 来自 `settings.BANNER_GET_DAILY_LIMIT`）：

```python
async def consume_banner_get_quota(user_id: int, db: AsyncSession) -> None:
    quota_date = today_local()
    limit = settings.BANNER_GET_DAILY_LIMIT
    tbl = BannerDailyGetQuota.__table__

    upsert = (
        insert(tbl)
        .values(
            user_id=user_id,
            quota_date=quota_date,
            request_count=1,
        )
        .on_conflict_do_update(
            index_elements=[tbl.c.user_id, tbl.c.quota_date],
            set_={
                "request_count": tbl.c.request_count + 1,
                "updated_at": func.now(),
            },
            where=tbl.c.request_count < limit,
        )
        .returning(tbl.c.request_count)
    )
    res = await db.execute(upsert)
    row = res.first()
    if row is not None:
        await db.commit()
        return

    from sqlalchemy import select

    current = await db.scalar(
        select(tbl.c.request_count).where(
            tbl.c.user_id == user_id,
            tbl.c.quota_date == quota_date,
        )
    )
    used = int(current or limit)
    resets_at = next_shanghai_midnight_after(quota_date)
    raise BusinessException(
        ErrorCode.BANNER_GET_RATE_LIMITED,
        data={
            "limit": limit,
            "used": used,
            "resets_at": resets_at.isoformat(),
        },
    )
```

注意：`app/db/session.py` 的 `get_db` **仅在异常时 rollback**，成功路径**不会**自动 `commit`。因此配额递增成功后必须 **`await db.commit()`**，与现有 `red_cut_card` 等服务写库方式一致。

3. 若 `RETURNING` 有行但 `request_count` 仍应校验：插入首条时 `request_count=1` 已在 values 中；冲突更新成功后应 ≤ `limit`。

- [ ] **Step 4: 调整测试与实现一致**

确保 mock 的 `execute` 顺序为：`upsert` 返回 `first() -> None`，然后 `scalar` 或第二次 `execute` 返回 `used=20`。若实现用 `db.scalar` 一次查询，则 `AsyncMock` 的 `side_effect` 为 `[exec_result, scalar_result]`。

- [ ] **Step 5: 运行测试**

运行: `python -m pytest tests/test_banner_quota_and_redcut.py -v`

预期: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/banner_service.py tests/test_banner_quota_and_redcut.py
git commit -m "feat: atomic banner GET daily quota consume"
```

---

### Task 6: 路由接入 `GET /banners`

**Files:**
- Modify: `app/api/v1/banner.py`

- [ ] **Step 1: 在 `get_banners` 内、读库前调用**

```python
    await banner_service.consume_banner_get_quota(current_user.id, db)
```

置于 `_parse_exclude_ids` 之后、`get_ready_cards` 之前。

- [ ] **Step 2: 手动验证**

启动应用后对同一登录用户连续请求 `GET /api/v1/banners` 超过配置次数，预期 `R.code == 40003` 且 `data` 含 `resets_at`。

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/banner.py
git commit -m "feat: enforce banner GET daily quota on list endpoint"
```

---

### Task 7: 红切标题仅最近 10 条

**Files:**
- Modify: `app/services/banner_service.py`

- [ ] **Step 1: 改写 `_red_cut_titles`**

将当前 `select(RecommendationCard.title).where(status==red_cut)` 改为：

- `order_by(RecommendationCard.red_cut_at.desc().nulls_last(), RecommendationCard.created_at.desc())`
- `.limit(10)`

返回 `list(result.scalars().all())`。

- [ ] **Step 2: Commit**

```bash
git add app/services/banner_service.py
git commit -m "feat: limit red-cut titles in banner prompt to 10 most recent"
```

---

### Task 8: OSS 按 URL 删除

**Files:**
- Modify: `app/services/oss_service.py`

- [ ] **Step 1: 实现 `delete_banner_object_by_url`**

```python
def delete_banner_object_by_url(image_url: str | None) -> None:
    if not image_url or not image_url.strip():
        return
    base = settings.OSS_BASE_URL.rstrip("/")
    url = image_url.strip()
    if not url.startswith(base + "/") and url != base:
        from loguru import logger
        logger.warning("banner oss delete skip: url not under OSS_BASE_URL prefix")
        return
    key = url[len(base) + 1 :] if url.startswith(base + "/") else ""
    if not key:
        return
    try:
        _bucket().delete_object(key)
    except Exception:
        from loguru import logger
        logger.exception("banner oss delete failed key={}", key[:120])
```

（不要在日志中打印完整 URL 若担心隐私；可对 key 截断。）

- [ ] **Step 2: Commit**

```bash
git add app/services/oss_service.py
git commit -m "feat: delete banner image from OSS by public URL"
```

---

### Task 9: 清理过期红切与 lifespan 调度

**Files:**
- Modify: `app/services/banner_service.py`
- Modify: `app/main.py`

- [ ] **Step 1: `cleanup_expired_red_cut_cards`**

在 `banner_service.py`：

```python
async def cleanup_expired_red_cut_cards(db: AsyncSession) -> int:
    import asyncio
    from datetime import timedelta, timezone

    from app.services import oss_service

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.BANNER_REDCUT_RETENTION_DAYS
    )
    batch = settings.BANNER_REDCUT_CLEANUP_BATCH_SIZE
    stmt = (
        select(RecommendationCard)
        .where(
            RecommendationCard.status == "red_cut",
            RecommendationCard.red_cut_at.is_not(None),
            RecommendationCard.red_cut_at < cutoff,
        )
        .limit(batch)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    for card in rows:
        await asyncio.to_thread(oss_service.delete_banner_object_by_url, card.image_url)
        await db.delete(card)
    if rows:
        await db.commit()
    return len(rows)
```

（清理任务在独立 `AsyncSessionLocal` 上下文中执行，批处理末尾 **`await db.commit()`** 与 Task 5 一致。）

- [ ] **Step 2: `app/main.py` lifespan**

在 `yield` 之前启动后台任务：

```python
import asyncio

from app.db.session import AsyncSessionLocal
from app.services import banner_service

async def _red_cut_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(settings.BANNER_REDCUT_CLEANUP_INTERVAL_SECONDS)
        try:
            async with AsyncSessionLocal() as db:
                n = await banner_service.cleanup_expired_red_cut_cards(db)
                if n:
                    logger.info("red-cut cleanup removed {} rows", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("red-cut cleanup loop error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(...)
    cleanup_task = asyncio.create_task(_red_cut_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await close_redis()
        logger.info(...)
```

需将 `lifespan` 改为 `try/finally` 结构以取消任务；若当前 `lifespan` 只有 `yield` 后 `close_redis`，则把 `close_redis` 移入 `finally`。

- [ ] **Step 3: Commit**

```bash
git add app/services/banner_service.py app/main.py
git commit -m "feat: periodic cleanup of expired red-cut banner cards"
```

---

### Task 10: 文档与规格状态（可选）

**Files:**
- Modify: `docs/superpowers/specs/2026-04-23-banner-rate-limit-redcut-retention-design.md`（将状态改为「已实现」并指向本 plan）

- [ ] **Step 1: 更新规格文末状态行**

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-23-banner-rate-limit-redcut-retention-design.md
git commit -m "docs: mark banner quota spec implemented"
```

---

## 计划自检（对照规格）

| 规格要求 | 对应 Task |
|----------|-----------|
| GET 每日 20 次、东八区重置 | Task 1, 2, 4, 5, 6 |
| 超限 BusinessException + `data` | Task 3, 5, 6 |
| 红切 7 天删库 + OSS，OSS 失败仍删库 | Task 8, 9 |
| 提示词红切最近 10 条 | Task 7 |
| 定时清理 | Task 9 |

**占位符扫描:** 本计划无 TBD/TODO 步骤；revision 文件名若冲突由执行者生成新 id。

**类型一致:** `consume_banner_get_quota(user_id, db)`；`cleanup_expired_red_cut_cards(db) -> int`。

---

**Plan 已保存至 `docs/superpowers/plans/2026-04-23-banner-rate-limit-redcut-retention.md`。执行方式二选一：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间评审，迭代快。  
2. **Inline Execution** — 本会话用 executing-plans 按检查点批量执行。

**你希望采用哪一种？**
