# Banner 推荐卡片生图链路可观测性设计

**日期:** 2026-04-23  
**状态:** 已评审（对话确认），待实现计划

## 背景与问题

推荐 banner 卡片通过 `generate_image_and_upload` 完成：调用 Ark 生图接口 → 下载临时图片 URL → `upload_banner_image` 写入阿里云 OSS。当前实现使用宽泛的 `except Exception: return None`，失败时上层仅表现为 `image_url` 为空，无法区分 Ark 请求失败、图片拉取失败还是 OSS 上传失败，排障成本高。

## 目标

1. 在**不改变对外契约**的前提下（`generate_image_and_upload` 仍返回 `str | None`），为三个阶段提供**可关联的日志**，便于定位真实失败点。
2. 在 `banner_service` 中对「有 `image_prompt` 但最终无图」的情况打**汇总告警级日志**，与 agent 内阶段日志配合排查。
3. 不引入新的 API 字段或前端协议变更；指标（Prometheus 等）不在本次范围，预留同一套阶段名即可。

## 非目标

- 不强制实现文案-only 降级策略或异步重试队列（可作为后续迭代）。
- 不在本次规范中修改 OSS 权限、AK/SK 配置来源；仅通过日志辅助发现配置/权限类问题。

## 架构与数据流

- **路径:** `app/agents/banner_agent.py` 中 `generate_image_and_upload`。
- **阶段划分:**
  - `ark_request`: `POST` Ark 生图接口，解析 `data[0].url`。
  - `image_fetch`: `GET` 临时图片 URL，读取 bytes。
  - `oss_upload`: 调用 `app/services/oss_service.upload_banner_image`。
- **调用方:** `app/services/banner_service.generate_cards` 在 `image_prompt` 存在时调用上述函数，并将返回值写入 `RecommendationCard.image_url`。

## 错误处理与日志约定

### `generate_image_and_upload`

- 使用与 `banner_service` 一致的 **`loguru` `logger`**。
- 每个阶段失败时记录**阶段标识**（建议使用统一前缀，例如 `banner_image:` + 阶段名），并对未预期异常使用 `logger.exception` 以保留堆栈。
- **禁止**在日志中输出 `Authorization` 头、完整 API Key 或 OSS Secret。
- **`image_prompt`** 如需记录，**截断**（建议约 80 字符）以防日志过大与过度暴露生成意图。
- OSS 阶段可记录 **bucket 名、endpoint**（来自已有 `settings`），便于对照控制台；不记录密钥。

### `banner_service.generate_cards`

- 当 `card.image_prompt` 非空且 `generate_image_and_upload` 返回 `None` 时，记录 **`logger.warning`**，包含 `user_id`、`card.id`，并说明卡片仍以 `status=ready` 入库但无图，便于与 agent 内阶段日志关联。

## 测试与验证

- **单元测试**（`banner_agent` 或现有 banner 测试文件）：通过 mock `httpx.AsyncClient` 与 mock `upload_banner_image`：
  - Ark 与拉图成功、OSS 抛错 → 返回 `None`，且日志（`caplog`）中出现 `oss_upload` 或规范中约定的阶段/前缀。
  - 可选：Ark 返回非 2xx → 返回 `None`，日志体现 `ark_request`。
- **手工验证:** 故意错误配置 OSS 凭证或 bucket，触发一次卡片生成，确认日志中能明确看到 `oss_upload` 相关错误，而非仅无图。

## 涉及文件（实现时）

- `app/agents/banner_agent.py` — 分阶段 try/except 与日志。
- `app/services/banner_service.py` — `image_url` 为 `None` 时的汇总 warning。
- `test/test_banner_service.py` 或针对 agent 的测试文件 — 新增/扩展用例与 `caplog`。

## 规范自检

- 无 TBD/TODO；行为边界（返回类型、不写密钥）已写明；范围限于可观测性，不含大范围重构。
