# Banner 推荐卡片：GET 日配额、红切保留与清理、提示词红切范围

**日期:** 2026-04-23  
**状态:** 已实现（见 `docs/superpowers/plans/2026-04-23-banner-rate-limit-redcut-retention.md`）

## 背景与目标

1. **限制**同一用户对推荐卡片列表接口的 **GET** 调用次数：**每天最多 20 次**；按 **Asia/Shanghai 自然日** 在本地 **午夜 12:00** 重置（即东八区日历日 `00:00` 起算新一日配额）。
2. **红切**（`recommendation_cards.status = red_cut`）记录在库中 **保留 7 天**（以 `red_cut_at` 为准）；超过保留期的行 **删除数据库记录**，并 **删除对应 OSS 对象**（由 `image_url` 解析）。**若 OSS 删除失败，仍删除数据库行**，并记录日志（避免僵尸行堆积；孤儿对象可通过 OSS 生命周期或运维补救）。
3. **生成卡片**时，提示词中的「已拒绝主题」**不再使用全量红切标题**，改为仅 **最近 10 条**（按 `red_cut_at` 降序；若历史数据无 `red_cut_at` 则用 `created_at` 降序兜底）。

## 非目标

- 不对 `POST /api/v1/banners/init`、`PUT /api/v1/banners/{id}/red-cut` 计入上述 20 次配额（除非产品后续明确要求）。
- 不改变 `GET /banners` 成功时的响应结构（`BannerListOut`）；配额用尽时通过业务错误返回（见下文）。
- 不在本规范中引入 Redis 等外部缓存；配额持久化使用 PostgreSQL。

## 架构概要

| 能力 | 位置（建议） | 说明 |
|------|----------------|------|
| 日配额计数 | 新表 + `banner_service` 或独立小模块 | `GET /banners` 入口在查卡前原子递增并校验上限 |
| 红切标题查询 | `banner_service._red_cut_titles`（或重命名） | 查询条件增加排序 + `LIMIT 10` |
| 过期红切清理 | 定时任务或启动时调度 + `banner_service` / `oss_service` | 批处理：解析 URL → 尝试删 OSS → 删 DB |

## 数据模型：日配额

**表名（建议）:** `banner_daily_get_quota`（或等价命名）

| 列 | 类型 | 说明 |
|----|------|------|
| `user_id` | FK → `users.id` | 与 `quota_date` 组成唯一键 |
| `quota_date` | `DATE` | **东八区**下的日历日（仅日期，无时区字段；写入时按 Shanghai 计算） |
| `request_count` | `INTEGER` | 当日已成功计数的 GET 次数 |
| `updated_at` | `TIMESTAMPTZ` | 可选，便于排查 |

**唯一约束:** `(user_id, quota_date)`。

**并发:** 使用单条 SQL 原子「若 `request_count < LIMIT` 则 +1 并返回新值，否则不增加」，避免多实例下超卖。实现可选用 PostgreSQL `INSERT ... ON CONFLICT DO UPDATE ... WHERE` + `RETURNING`，或等价可序列化逻辑；具体 SQL 在实现计划中给出。

**配置:** `BANNER_GET_DAILY_LIMIT` 默认 `20`（`.env` / `settings`），便于环境差异与测试调小。

## API 行为：`GET /api/v1/banners`

1. 认证通过后，计算当前用户在 **Asia/Shanghai** 下的 `quota_date`。
2. 尝试原子递增计数；若递增后仍 `<= BANNER_GET_DAILY_LIMIT`，则继续执行现有 `get_ready_cards` 逻辑。
3. 若已达上限，**不**递增（或递增失败分支），抛出 `BusinessException`，与项目惯例一致（见 `README`：业务异常用 `BusinessException`，不直接 `HTTPException`）。
4. **建议**新增 `ErrorCode`（例如 `BANNER_GET_RATE_LIMITED`，数值在 `4xxxx` 段与现有食物/日志错误并列），`message` 为简短中文说明；`data` 可选携带 `limit`、`used`、`resets_at`（下一东八区自然日开始时刻的 ISO 8601），便于客户端展示「次日可再试」。**HTTP 状态码**维持与现有 `BusinessException` 处理器一致（当前为 **200 + `R.code`**）；若未来全局改为 429，可单列迁移任务，不在本功能中强行分叉。

## 红切清理任务

**选中条件:** `status = 'red_cut'` 且 `red_cut_at` **不为空** 且 `red_cut_at < now_utc - 7 days`（7 天按 **日历/时间间隔** 使用 UTC 存储的 `timestamptz` 比较即可，与「东八区日配额」独立）。

**单条处理顺序:**

1. 若 `image_url` 非空，调用现有 OSS 删除能力（若尚无则新增 `delete_banner_object` 一类函数，与 `upload_banner_image` 使用相同 bucket/路径规则解析 object key）。
2. **无论 OSS 是否成功**，删除该 `recommendation_cards` 行。
3. OSS 失败时 `logger.warning` 或 `logger.error`，包含 `card_id`、`user_id`、截断后的 URL，**禁止**记录密钥。

**调度:** 仓库当前无通用调度器；实现可选用其一并在计划中定稿：

- **A（推荐）:** FastAPI `lifespan` 中启动 `asyncio` 后台循环，每 **1 小时**（或可配置）执行一批；或每日固定在东八区低峰执行。
- **B:** 运维 **cron** 调用 `python -m app.jobs.cleanup_red_cut_banners`（或等价 CLI）。

批大小上限（如每次最多 500 行）避免长事务。

## 提示词：已拒绝主题范围

- 替换当前「该用户所有 `red_cut` 标题」为：**按 `red_cut_at DESC NULLS LAST, created_at DESC` 取前 10 条** `title`。
- `format_banner_content_prompt` 入参仍为 `list[str]`，由调用方保证最多 10 条，**无需**改 prompt 模板结构。

## 测试要点

- 配额：同一 `user_id` 在东八区边界（如 23:59 → 00:00）前后计数重置；第 20 次成功、第 21 次失败。
- 红切查询：超过 10 条红切时仅最近 10 条进入生成流程。
- 清理：构造 `red_cut_at` 早于 8 天的行，任务执行后行删除；OSS mock 失败时行仍删除。

## 与既有文档关系

- 延续 [2026-04-22-recommendation-cards-design.md](./2026-04-22-recommendation-cards-design.md) 中的 banner / 红切语义；本规范是对**流量控制、数据生命周期与 prompt 体量**的增量约束。

## 决策记录（对话确认）

| 项 | 结论 |
|----|------|
| 每日 GET 上限 | 20 |
| 重置时刻 | Asia/Shanghai 自然日午夜 |
| 红切保留 | 7 天后清理 |
| 提示词红切条数 | 最近 10 条标题 |
| OSS 删除失败 | **仍删除 DB 行** |
