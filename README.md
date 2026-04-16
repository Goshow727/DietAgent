# dietAgent_demo1

FastAPI + LangGraph + SQLAlchemy + PostgreSQL (pgvector) + Redis + PyJWT 膳食 Agent 脚手架。

## 技术栈

- **Web**: FastAPI (async), uvicorn
- **Agent**: LangGraph + Qwen (DashScope OpenAI 兼容接口)
- **存储**: PostgreSQL (async via asyncpg) + pgvector 向量扩展
- **缓存**: Redis
- **认证**: PyJWT + passlib bcrypt
- **配置**: pydantic-settings (`.env`)
- **日志**: loguru + trace_id 中间件
- **迁移**: Alembic (async 模板)
- **包管理**: uv

## 项目结构

```
app/
├── api/v1/        # 路由层 (auth / user / agent / health)
├── core/          # 配置/响应/异常/安全/日志/中间件
├── db/            # async engine, session, redis client
├── models/        # SQLAlchemy ORM
├── schemas/       # pydantic 入参/出参
├── services/      # 业务逻辑
├── agents/        # LangGraph 图定义
└── main.py        # create_app 工厂
alembic/           # 数据库迁移
main.py            # uvicorn 入口
```

## 统一响应结构

所有接口返回 `code + message + data` JSON：

```json
{ "code": 0, "message": "ok", "data": { ... } }
```

业务错误返回非零 code（`app/core/error_code.py`），HTTP 状态保持 200；参数校验、未登录、未知异常均被全局 handler 捕获转为统一结构（`app/core/exceptions.py`）。

## 快速开始

### 1. 准备数据库

项目假定 PostgreSQL 已在本机/WSL 运行。需要：

```sql
CREATE DATABASE dietagent;
\c dietagent
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. 准备 Redis

```bash
docker compose up -d redis
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，按本机实际修改 `DATABASE_URL`、`JWT_SECRET`、`DASHSCOPE_API_KEY`。

### 4. 安装依赖

```bash
uv sync
```

### 5. 数据库迁移

```bash
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
```

### 6. 启动服务

```bash
uv run python main.py
```

访问 http://localhost:8000/docs 查看 Swagger。

## 示例接口

| 方法 | 路径 | 说明 |
| - | - | - |
| GET  | `/api/v1/health` | 健康检查（验证 DB + Redis 连通） |
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录，获取 JWT |
| GET  | `/api/v1/users/me` | 当前用户（需 Bearer Token） |
| POST | `/api/v1/agent/chat` | 调用 LangGraph diet agent（需 Bearer Token） |

## 开发约定

- 业务异常用 `BusinessException(ErrorCode.XXX)`，不要直接 `raise HTTPException`。
- 新增错误码到 `app/core/error_code.py`，并在 `ERROR_MESSAGES` 登记中文消息。
- 新路由在 `app/api/v1/` 下新建文件，并在 `router.py` 中 `include_router`。
- 响应统一使用 `R.ok(...)` / `R.fail(...)`。
