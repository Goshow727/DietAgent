# Banner 饮食推荐联网（enable_search）设计

**日期:** 2026-04-23  
**状态:** 已评审（对话确认「1」），待实现计划

## 背景与问题

推荐 banner 卡片文案由 `app/agents/banner_agent.py` 中 `generate_card_drafts` 调用 DashScope 兼容模式（`ChatOpenAI` + `DASHSCOPE_BASE_URL`）完成，当前为**单次** `ainvoke`，无联网。业务希望在生成饮食推荐时允许模型使用**大模型服务侧**的网络检索能力，做法是：在**请求体**中传入 `enable_search: true`（以服务商文档为准，字段名/层级以文档为最终依据）。

**术语澄清：** 产品上的「可联网推荐」在工程上落实为**该次补全/对话请求**打开联网，**不**在应用内再实现独立 HTTP 的 `search_web` 工具 + LangChain 多轮显式 tool 循环，除非未来产品要求与平台能力不满足时再评估。

## 目标

1. 在 **仅 Banner 卡片草稿生成** 这条链路上，当配置允许时，向模型请求**透传** `enable_search: true`（或文档规定的等价方式），使模型在生成 `title` / `desc` / `image_prompt` 等时能够按需检索公网信息。
2. 通过 **环境配置** 可在开发/单测/生产关闭联网，避免额外费用与不稳定的 CI 外网依赖；关闭时行为与**当前**（不联网）一致。
3. 在提示词中约束：**联网仅作辅助**，不替代 RAG/用户摘要以外的安全与合规边界，不把网页未验证内容当作医学诊断。

## 非目标

- 不实现自托管搜索 API（Tavily、SerpAPI 等）或 LangChain `StructuredTool` 形式的**独立**搜索 step（与本 spec 的「请求体开关」方式无关的可选增强不在此包）。
- 不修改 GET `/banners` 等**对外 API** 的 JSON 协议；不强制在前端暴露「是否联网」开关（若后续要暴露，单独立项）。
- 不保证「可观测的 N 次搜索」；次数与策略由**服务商**在单次已启用联网的请求内实现。

## 架构与数据流

- **入口不变：** `app/services/banner_service.py` 中 `generate_cards` 仍组装 RAG 片段、身体信息、近 7 天饮食/运动摘要、`red_cut_titles` 等，并调用 `generate_card_drafts(...)`。
- **变更点：** `generate_card_drafts` 使用的 LLM 客户端在 `settings.BANNER_ENABLE_NETWORK_SEARCH` 为 `True` 时，在调用 OpenAI 兼容接口时携带 **`enable_search: true`**（若 LangChain 的 `ChatOpenAI` 不直接支持该参数，则通过其支持的 `model_kwargs` 或 `extra_body` 等机制透传；**实现前**以 DashScope 兼容模式最新文档确认字段名与位置）。
- **输出契约不变：** 仍为可解析的 JSON 列表，字段与现有一致；不在此 spec 中引入「第二次独立 LLM 调用」的必选流程。若需「先规划查询再写卡」的拆步，属后续增强。

**推荐实现结构：** 增加专用工厂函数，例如 ` _get_llm_for_banner() `（或向现有 `_get_llm` 增加可选参数，但须避免影响 `diet_agent` 等其它调用方），使**仅** Banner 路径携带联网开关与（若需）可区分的 `temperature` 等；**不**用 `@lru_cache` 缓存「带/不带联网」两种客户端时若会串配置，需二选一或按参数区分缓存键。

## 配置

- 新增设置项，例如 `BANNER_ENABLE_NETWORK_SEARCH: bool = False`（或默认 `True` 由产品决定；**本 spec 建议默认 `False`** 以减少意外费用，部署时再显式打开）。
- 与现有 `DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、`QWEN_MODEL` 共用同一边缘；不新增第二套 key，除非以后单独模型。

## 提示词与安全

- 在 `BANNER_CONTENT_SYSTEM` 与/或 `format_banner_content_prompt` 中增加简短规则：**优先**依据所给指南片段与用户近 7 天摘要、身体信息；联网内容用于**补充**时效或常识，须表述为**科普性、个体化建议**；**禁止**将网页内容作为确诊、疗效承诺、替代专业医疗；遇冲突时**以 RAG/摘要与平台安全策略为准**。
- 日志：禁止打印完整带密钥的请求体；若需调试联网是否生效，仅用脱敏/布尔标记。

## 错误处理与降级

- 若因联网导致超时、4xx/5xx 或解析失败：记录 **warning 或 error**（含 `user_id` 若可取得），**策略建议：** 对**同一**草稿生成**最多一次**重试，第二次尝试**关闭** `enable_search` 再请求，避免因联网长期阻塞补池；若仍失败，与当前一致：`generate_cards` 打错误日志并**跳过/中止**本批（与现 `generate_card_drafts` 异常处理一致，不在此 spec 改变既有 `try/except` 外层语义，除非实现时发现必须细化）。
- 接受联网带来的**延迟与费用**略增；`ensure_pool` 批量补卡场景下在运维上关注峰值。

## 测试与验证

- **单元测试：** Mock LLM 或 `ChatOpenAI` 构造，断言在 `BANNER_ENABLE_NETWORK_SEARCH=True` 时，发往模型的参数中包含 `enable_search` 或等价的 `extra_body`；为 `False` 时不包含。CI **不**依赖真实外网联网。
- **手工验证：** 在测试环境打开开关，触发生成一张卡片，确认文案质量与无异常链断裂（无需在 spec 中规定具体关键词）。

## 涉及文件（实现时）

- `app/core/config.py` — 新增 `BANNER_ENABLE_NETWORK_SEARCH`。
- `app/agents/banner_agent.py` — 构造带联网开关的 LLM 并用于 `generate_card_drafts`。
- `app/prompts/banner_content.py`（或同目录相关文件）— 补充安全与优先级说明。
- 测试：针对 `banner_agent` 或 config 的 mock 用例（路径与现有 `test/` 结构对齐）。

## 规范自检

- 联网开关以**配置**与**服务文档**为准；若文档中字段非顶层 `enable_search`，在实现 PR 中更新本句或附录**一行**说明实际透传方式，避免长期歧义。
- 无与「不实现独立 search tool」相矛盾的要求；范围限于 Banner 文案生成链路与提示词/降级。
