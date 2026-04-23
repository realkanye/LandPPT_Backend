# LandPPT 部署与配置指南

## 目录

- [依赖服务](#依赖服务)
- [环境变量配置](#环境变量配置)
- [启动项目](#启动项目)
- [API 接口说明](#api-接口说明)
- [注意事项](#注意事项)

---

## 依赖服务

| 服务 | 版本要求 | 是否必须 | 说明 |
|------|---------|---------|------|
| **MongoDB** | 6.x / 7.x | ✅ 必须 | 主数据库，存储项目、幻灯片、模板等数据 |
| **Valkey / Redis** | 7.x / 8.x | ⚠️ 可选 | 分布式缓存；不配置则降级为进程内内存缓存（功能正常，重启后缓存丢失） |
| **Python** | 3.11+ | ✅ 必须 | 运行时 |

> **注意**：原 PostgreSQL 已完全移除，无需安装。

---

## 环境变量配置

将 `.env.example` 复制为 `.env` 并填写以下关键字段：

```bash
cp .env.example .env
```

### 必填项

```env
# MongoDB 连接（必须）
MONGODB_URL=mongodb://user:password@host:27017/landppt

# 应用密钥（必须，生产环境请换成随机长字符串）
SECRET_KEY=your-random-secret-key-here

# 至少配置一个 AI 提供商
DEFAULT_AI_PROVIDER=openai          # openai | anthropic | google | ollama
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

### 可选项

```env
# 缓存（不配置则用内存缓存）
CACHE_BACKEND=valkey                 # valkey | memory
VALKEY_URL=valkey://127.0.0.1:6379

# 服务器
HOST=0.0.0.0
PORT=8000
WORKERS=2                            # 生产环境建议 2-4；reload=true 时自动强制为 1
RELOAD=false                         # 开发时设为 true，生产设为 false
LOG_LEVEL=info                       # debug | info | warning | error

# 认证
DISABLE_AUTH=false                   # true = 无需登录（API-only 模式）
LANDPPT_ENABLE_API_DOCS=true         # 是否暴露 /docs Swagger UI

# 其他 AI 提供商（按需配置）
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

GOOGLE_API_KEY=
GOOGLE_MODEL=gemini-2.5-flash

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2
```

### MongoDB URL 格式

```
# 无认证（本地开发）
MONGODB_URL=mongodb://localhost:27017/landppt

# 有用户名密码
MONGODB_URL=mongodb://username:password@host:27017/landppt?authSource=admin

# 副本集
MONGODB_URL=mongodb://user:pass@host1:27017,host2:27017/landppt?replicaSet=rs0

# MongoDB Atlas
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/landppt
```

---

## 启动项目

### 方式一：直接用 Python 启动（推荐开发/测试）

```bash
# 安装依赖（首次）
pip install uv
uv sync --no-dev --frozen

# 启动
python run.py
```

启动后访问：
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

### 方式二：uvicorn 直接启动

```bash
PYTHONPATH=src uvicorn landppt.main_api:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 2
```

### 方式三：Docker（按公司 Dockerfile 模板构建）

```bash
# 构建镜像
docker build -t landppt:latest .

# 启动（需要先有运行中的 MongoDB）
docker run -d \
  --name landppt \
  -p 8000:8000 \
  -v $(pwd)/.env:/app/.env \
  -e MONGODB_URL=mongodb://mongo-host:27017/landppt \
  landppt:latest
```

---

## API 接口说明

所有接口均有 Swagger 文档，启动后访问 `/docs` 查看完整说明。

### v1 推荐接口（异步任务模式）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/presentations` | 提交 PPT 生成任务，返回 `job_id` |
| `GET` | `/v1/jobs/{job_id}` | 查询任务状态（pending → running → completed） |
| `GET` | `/v1/presentations/{project_id}/download` | 下载结果（`?format=html\|pdf\|pptx`） |
| `POST` | `/v1/files/upload` | 上传文档，返回 `processed_content` 供生成使用 |
| `GET` | `/v1/scenarios` | 获取支持的场景列表 |
| `GET` | `/v1/health` | v1 健康检查 |

### 基础接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 全局健康检查 |
| `GET` | `/projects` | 项目列表 |
| `POST` | `/projects` | 创建项目 |
| `GET` | `/projects/{id}` | 获取项目详情 |
| `DELETE` | `/projects/{id}` | 删除项目 |
| `POST` | `/generate` | 同步生成（阻塞，不推荐用于生产） |

---

## 注意事项

### 首次启动

- 应用启动时会**自动初始化 MongoDB 集合和索引**，无需手动建表或执行迁移脚本。
- 会自动从 `template_examples/` 目录导入 25 个内置 PPT 模板到 MongoDB。
- 如果 MongoDB 不可连接，启动会失败并报错（不会静默忽略）。

### 多进程部署

- `WORKERS > 1` 时，数据库初始化（建索引、导入模板）通过**文件锁**保证只执行一次，不会重复导入。
- `WORKERS > 1` 时 `RELOAD` 会自动强制关闭。

### 配置说明

- 原 `DATABASE_URL`（PostgreSQL）**已废弃**，配置了也无效，请删除。
- AI 相关配置（API Key、模型等）也可以在应用启动后通过 **Settings 页面** 动态修改，存储在 MongoDB 的 `user_configs` 集合中，无需重启。

### 已知限制（当前版本）

- `docker-compose.yml` 文件仍为旧版 PostgreSQL 配置，**请勿直接使用**，等待公司统一 Dockerfile 模板后更新。
- Playwright（PPT 导出 PDF 功能）需要 Chromium，Dockerfile 构建阶段会自动安装；本地直接运行需要额外执行 `playwright install chromium`。
- 同步生成接口（`/generate`）不适合生产，建议统一使用 `/v1/presentations` 异步接口。
