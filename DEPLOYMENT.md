# LandPPT 部署与配置指南

## 目录

- [依赖服务](#依赖服务)
- [环境变量配置](#环境变量配置)
- [启动项目](#启动项目)
- [获取生成的 PPT 文件](#获取生成的-ppt-文件)
- [API 接口说明](#api-接口说明)
- [注意事项](#注意事项)

---

## 依赖服务

| 服务 | 版本要求 | 是否必须 | 说明 |
|------|---------|---------|------|
| **MongoDB** | 6.x / 7.x | ✅ 必须 | 主数据库，存储项目、幻灯片、模板等数据 |
| **Valkey / Redis** | 7.x / 8.x | ⚠️ 可选 | 分布式缓存；不配置则降级为进程内内存缓存（功能正常，重启后缓存丢失） |
| **Python** | 3.11+ | ✅ 必须 | 运行时 |
| **Chromium / Playwright** | 最新 | ⚠️ 仅导出 PDF/PPTX 时需要 | 见"获取生成的 PPT 文件"一节 |

> **注意**：原 PostgreSQL 已完全移除，无需安装。

---

## 环境变量配置

将 `.env.example` 复制为 `.env` 并填写以下字段：

```bash
cp .env.example .env
```

### 必填项

```env
# MongoDB 连接
MONGODB_URL=mongodb://localhost:27017/landppt

# 选择默认 AI 提供商（见下方各提供商配置）
DEFAULT_AI_PROVIDER=openai
```

---

### AI 提供商配置（至少配置一个）

#### OpenAI / 兼容 OpenAI 接口的代理

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1   # 使用代理时改为代理地址
OPENAI_MODEL=gpt-4o
```

> 若使用国内中转或私有部署的 OpenAI 兼容接口，只需修改 `OPENAI_BASE_URL` 即可，其余不变。

#### Anthropic Claude

```env
ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_BASE_URL=https://api.anthropic.com   # 使用代理时修改此项
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
```

#### Google Gemini

```env
GOOGLE_API_KEY=AIza-xxx
GOOGLE_BASE_URL=https://generativelanguage.googleapis.com   # 使用代理时修改此项
GOOGLE_MODEL=gemini-2.5-flash
```

#### Azure OpenAI

```env
AZURE_OPENAI_API_KEY=your-azure-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

> 使用 Azure 时将 `DEFAULT_AI_PROVIDER=azure_openai`。

#### Ollama（本地模型）

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2
```

> 使用 Ollama 时将 `DEFAULT_AI_PROVIDER=ollama`。

---

### 可选项

```env
# 缓存（不配置则用内存缓存，重启后丢失）
CACHE_BACKEND=memory                 # memory | valkey
VALKEY_URL=valkey://127.0.0.1:6379

# 服务器
HOST=0.0.0.0
PORT=8000
WORKERS=2                            # 生产环境建议 2-4；reload=true 时自动强制为 1
RELOAD=false                         # 开发时 true，生产 false
LOG_LEVEL=info

# 认证
DISABLE_AUTH=false                   # true = 无需登录（纯 API 模式）
LANDPPT_ENABLE_API_DOCS=true         # 是否暴露 /docs Swagger UI

# 联网搜索（用于大纲生成时联网补充内容）
TAVILY_API_KEY=your_tavily_key_here
```

---

### PPT 导出配置（可选）

系统默认以 **HTML** 格式存储和提供 PPT 内容（无需额外配置）。
若需导出为 **PDF** 或 **PPTX**，则需以下配置：

#### PDF 导出（需要 Playwright）

PDF 导出通过 Chromium 无头浏览器将 HTML 渲染为 PDF，需要在宿主机安装 Playwright：

```bash
# 安装 Playwright Chromium（首次部署执行一次）
.venv/bin/playwright install chromium
```

无需额外环境变量，启用后即可通过 API 提交 PDF 导出任务。

#### PPTX 导出（需要 Playwright + Apryse SDK）

PPTX 导出流程：HTML → PDF（Playwright）→ PPTX（Apryse SDK 转换）。

需在 `.env` 中启用并填写 Apryse 授权 Key：

```env
ENABLE_APRYSE_PPTX_EXPORT=true
APRYSE_LICENSE_KEY=your_apryse_license_key_here
```

> Apryse License Key 请前往 [https://docs.apryse.com/](https://docs.apryse.com/) 获取。
> Apryse SDK 文件会在首次调用导出接口时**自动从官方地址下载**，无需手动安装。
> 若未配置此项，PPTX 导出接口会返回明确的错误提示，其余功能不受影响。

---

## MongoDB URL 格式

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
docker build -t landppt:latest .
docker run -d \
  --name landppt \
  -p 8000:8000 \
  -v $(pwd)/.env:/app/.env \
  -e MONGODB_URL=mongodb://mongo-host:27017/landppt \
  landppt:latest
```

---

## 获取生成的 PPT 文件

PPT 生成完成后，支持三种格式下载：

### 格式对比

| 格式 | 接口 | 前置条件 | 说明 |
|------|------|---------|------|
| **HTML** | `GET /v1/presentations/{id}/download?format=html` | 无 | 默认格式，立即返回，可在浏览器打开 |
| **PDF** | 异步导出（见下） | 需要 Playwright | 通过 Chromium 渲染为 PDF |
| **PPTX** | 异步导出（见下） | 需要 Playwright + Apryse Key | PDF 经 Apryse SDK 转换为 .pptx |

### HTML 下载（无需额外配置）

```bash
# 生成完成后直接下载 HTML
curl -o presentation.html \
  "http://localhost:8000/v1/presentations/{project_id}/download?format=html"
```

### PDF / PPTX 异步导出流程

```bash
# 步骤 1：提交导出任务（format=pdf 或 format=pptx）
curl -X POST \
  "http://localhost:8000/v1/presentations/{project_id}/exports?format=pdf"
# 返回: {"job_id": "export-xxx", ...}

# 步骤 2：轮询导出状态
curl "http://localhost:8000/v1/jobs/{export_job_id}"
# 等待 status 变为 "completed"

# 步骤 3：下载文件
curl -o output.pdf \
  "http://localhost:8000/v1/jobs/{export_job_id}/download"
```

---

## API 接口说明

所有接口均有 Swagger 文档，启动后访问 `/docs` 查看完整说明。

### v1 推荐接口（异步任务模式）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/presentations` | 提交 PPT 生成任务，返回 `job_id` + `project_id` |
| `GET` | `/v1/jobs/{job_id}` | 查询任务状态（pending → running → completed） |
| `GET` | `/v1/presentations/{id}/download` | 下载 HTML（`?format=html`，生成完成后可用） |
| `POST` | `/v1/presentations/{id}/exports` | 提交 PDF/PPTX 导出任务（`?format=pdf\|pptx`） |
| `GET` | `/v1/jobs/{export_job_id}/download` | 下载导出的 PDF/PPTX 文件 |
| `POST` | `/v1/files/upload` | 上传文档，返回 `processed_content` 供生成使用 |
| `GET` | `/v1/scenarios` | 获取支持的场景列表 |
| `GET` | `/outline/generate` | 大纲生成（同步，秒级返回） |

### 基础接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 全局健康检查 |
| `GET` | `/projects` | 项目列表 |
| `GET` | `/projects/{id}` | 获取项目详情 |
| `DELETE` | `/projects/{id}` | 删除项目 |

---

## 注意事项

### 首次启动

- 应用启动时会**自动初始化 MongoDB 集合和索引**，无需手动建表或执行迁移脚本。
- 会自动从 `template_examples/` 目录导入 25 个内置 PPT 模板到 MongoDB。
- 如果 MongoDB 不可连接，启动会失败并报错（不会静默忽略）。

### 多进程部署

- `WORKERS > 1` 时，数据库初始化（建索引、导入模板）通过**文件锁**保证只执行一次，不会重复导入。
- `WORKERS > 1` 时 `RELOAD` 会自动强制关闭。

### 存储说明

- 项目仅使用 **MongoDB** 一种持久化存储，无 PostgreSQL / SQLite 依赖。
- Valkey（Redis）仅用于缓存加速，不存储业务数据，可选。

### AI 模型说明

- `DEFAULT_AI_PROVIDER` 决定主要使用哪个 AI 服务商。
- 各提供商的 `*_BASE_URL` 字段支持配置为任意兼容接口的代理地址，方便国内网络环境使用。
- 通过 `DEFAULT_MODEL_PROVIDER` / `DEFAULT_MODEL_NAME` 等角色覆盖变量可为大纲、幻灯片生成等不同阶段指定不同模型。

### 已知限制（当前版本）

- `docker-compose.yml` 仍为旧版配置，**请勿直接使用**，等待公司统一 Dockerfile 模板后更新。
- PPTX 导出需要 Apryse License Key（商业授权），未配置时其他功能不受影响。
- 同步生成接口（`/generate`）不适合生产，建议统一使用 `/v1/presentations` 异步接口。
