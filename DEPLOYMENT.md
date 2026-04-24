# LandPPT 部署指南

本文档介绍如何在服务器上部署 LandPPT，包括环境要求、依赖安装、配置参数和启动方式。

> 接口调用方式请参阅 [API_README.md](./API_README.md)。

---

## 目录

1. [环境要求](#1-环境要求)
2. [获取代码](#2-获取代码)
3. [安装 Python 依赖](#3-安装-python-依赖)
4. [配置环境变量](#4-配置环境变量)
5. [启动服务](#5-启动服务)
6. [使用 Docker 部署](#6-使用-docker-部署)
7. [验证部署](#7-验证部署)
8. [可选功能配置](#8-可选功能配置)
9. [注意事项](#9-注意事项)

---

## 1. 环境要求

### 必须

| 组件 | 版本要求 | 说明 |
|---|---|---|
| **Python** | 3.11 或 3.12 | 运行时，低于 3.11 不支持 |
| **MongoDB** | 6.x 或 7.x | 唯一持久化存储，所有数据存于此 |
| **AI 提供商** | — | 至少配置一个（见第 4 节） |

### 可选

| 组件 | 说明 |
|---|---|
| **Valkey / Redis** 7.x+ | 分布式缓存；不配置则自动降级为进程内内存缓存，功能正常，重启后缓存丢失 |
| **Playwright（Chromium）** | 仅导出 PDF / PPTX 时需要 |
| **Apryse SDK** | 仅导出 PPTX 时需要，需申请商业 License Key |

> **无 PostgreSQL / SQLite 依赖。** 项目已完全切换为 MongoDB，无需安装其他数据库。

---

## 2. 获取代码

```bash
git clone <your-repo-url> LandPPT_Backend
cd LandPPT_Backend
```

---

## 3. 安装 Python 依赖

推荐使用 `uv`（速度更快）：

```bash
# 安装 uv（若未安装）
pip install uv

# 创建虚拟环境并安装所有依赖（使用 pyproject.toml 锁定版本）
uv sync --no-dev --frozen
```

如果使用标准 `pip`：

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows

pip install -e .
```

依赖安装完成后，如需使用 PDF / PPTX 导出功能，还需安装 Playwright 浏览器：

```bash
# 安装 Chromium（仅首次，约 200MB）
.venv/bin/playwright install chromium

# Linux 服务器通常还需要以下系统依赖
.venv/bin/playwright install-deps chromium
```

---

## 4. 配置环境变量

复制示例文件并编辑：

```bash
cp .env.example .env
```

以下各小节分别说明必填项和可选项。

---

### 4.1 必填：数据库

```env
# MongoDB 连接地址
MONGODB_URL=mongodb://localhost:27017/landppt
```

**常见格式：**

```env
# 本地无认证（开发环境）
MONGODB_URL=mongodb://localhost:27017/landppt

# 带用户名密码
MONGODB_URL=mongodb://username:password@host:27017/landppt?authSource=admin

# 副本集
MONGODB_URL=mongodb://user:pass@host1:27017,host2:27017/landppt?replicaSet=rs0

# MongoDB Atlas（云服务）
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/landppt
```

---

### 4.2 必填：AI 提供商

必须至少配置一个 AI 提供商，并通过 `DEFAULT_AI_PROVIDER` 指定默认使用哪个。

```env
# 选择默认 AI 提供商
# 可选值：openai | anthropic | google | azure_openai | ollama
DEFAULT_AI_PROVIDER=openai
```

#### OpenAI（及兼容 OpenAI 接口的服务）

```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o
# 若使用国内中转或私有代理，修改此地址即可：
OPENAI_BASE_URL=https://api.openai.com/v1
```

#### Anthropic Claude

```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
# 使用代理时修改此项：
ANTHROPIC_BASE_URL=https://api.anthropic.com
```

#### Google Gemini

```env
GOOGLE_API_KEY=AIzaxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_MODEL=gemini-2.5-flash
# 使用代理时修改此项：
GOOGLE_BASE_URL=https://generativelanguage.googleapis.com
```

#### Azure OpenAI

```env
DEFAULT_AI_PROVIDER=azure_openai

AZURE_OPENAI_API_KEY=your-azure-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

#### Ollama（本地模型）

```env
DEFAULT_AI_PROVIDER=ollama

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

> 使用 Ollama 前需先在本机安装并拉取模型：`ollama pull llama3`

---

### 4.3 可选：服务器参数

```env
HOST=0.0.0.0          # 监听地址，0.0.0.0 表示所有网卡
PORT=8000             # 监听端口
WORKERS=2             # 进程数，生产建议 2~4；开发时设为 1
RELOAD=false          # 热重载，开发时可改为 true，生产必须 false
LOG_LEVEL=info        # 日志级别：debug | info | warning | error
```

---

### 4.4 可选：缓存（Valkey / Redis）

不配置时自动使用进程内内存缓存，功能正常，多进程间缓存不共享。

```env
CACHE_BACKEND=valkey              # memory（默认）| valkey
VALKEY_URL=valkey://127.0.0.1:6379
```

---

### 4.5 可选：联网搜索增强

开启后，大纲生成阶段可通过搜索引擎补充最新资料（请求时传 `network_mode=true`）。

#### Tavily（推荐）

```env
RESEARCH_PROVIDER=tavily
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxx
# 申请地址：https://tavily.com/
```

#### SearXNG（自建搜索实例）

```env
RESEARCH_PROVIDER=searxng
SEARXNG_HOST=http://your-searxng-instance:8888
```

---

### 4.6 可选：图片服务

控制幻灯片中是否插入图片，以及图片来源。

```env
ENABLE_IMAGE_SERVICE=false         # 总开关，false 时不插入任何图片

# 启用后可选择图片来源：
ENABLE_NETWORK_SEARCH=true         # 网络图片搜索（Pixabay / Unsplash）
ENABLE_AI_GENERATION=false         # AI 生图（需配置对应 API Key）

# 网络图片 API Key（任选其一或同时配置）
PIXABAY_API_KEY=your-pixabay-key           # 申请：https://pixabay.com/api/docs/
UNSPLASH_ACCESS_KEY=your-unsplash-key      # 申请：https://unsplash.com/developers

# AI 图片生成（Pollinations，免费无需 Key）
ENABLE_AI_GENERATION=true
DEFAULT_AI_IMAGE_PROVIDER=pollinations
```

---

### 4.7 可选：LLM 请求参数

```env
MAX_TOKENS=8192         # 单次 LLM 最大生成 Token 数
TEMPERATURE=0.7         # 生成温度（0.0=确定性，1.0=创意性）
LLM_TIMEOUT_SECONDS=600 # LLM 请求超时（秒），生成大型 PPT 可能需要较长时间
```

---

### 4.8 可选：分阶段指定不同模型

可为大纲生成、幻灯片生成等不同阶段单独指定模型，留空则沿用默认。

```env
# 格式：提供商名称（同 DEFAULT_AI_PROVIDER 可选值）
OUTLINE_MODEL_PROVIDER=openai
OUTLINE_MODEL_NAME=gpt-4o

SLIDE_GENERATION_MODEL_PROVIDER=anthropic
SLIDE_GENERATION_MODEL_NAME=claude-3-5-haiku-20241022
```

---

### 4.9 可选：PDF / PPTX 导出

系统默认以 HTML 格式输出，无需额外配置即可下载。导出为 PDF 或 PPTX 需要以下配置：

#### PDF 导出

需要已安装 Playwright Chromium（见第 3 节），无需额外环境变量。

#### PPTX 导出

PPTX 转换链路：HTML → PDF（Playwright）→ PPTX（Apryse SDK）。

```env
ENABLE_APRYSE_PPTX_EXPORT=true
APRYSE_LICENSE_KEY=your-apryse-license-key
# License Key 申请：https://docs.apryse.com/
```

> Apryse SDK 会在首次调用导出接口时自动下载，无需手动安装。

---

### 4.10 API 文档开关

```env
LANDPPT_ENABLE_API_DOCS=true   # true=暴露 /docs Swagger UI，false=关闭
```

---

## 5. 启动服务

### 方式一：run.py（推荐，自动读取 .env）

```bash
# 激活虚拟环境（uv sync 创建的）
source .venv/bin/activate

python run.py
```

启动成功后输出示例：

```
Starting LandPPT Server...
Host: 0.0.0.0
Port: 8000
Workers: 2
Server will be available at: http://localhost:8000
```

### 方式二：uvicorn 直接启动

```bash
PYTHONPATH=src uvicorn landppt.main_api:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 2
```

### 方式三：后台运行（生产环境）

```bash
# 使用 nohup 后台运行，日志写入文件
nohup python run.py > logs/landppt.log 2>&1 &
echo $! > landppt.pid

# 查看日志
tail -f logs/landppt.log

# 停止服务
kill $(cat landppt.pid)
```

> 生产环境推荐配合 **systemd** 或 **supervisor** 进行进程管理，确保崩溃自动重启。

---

## 6. 使用 Docker 部署

项目提供了 `docker-compose.yml`，配合 `.env` 文件即可一键启动。

### 准备 .env 文件

```bash
cp .env.example .env
# 编辑 .env，至少填写：
#   MONGODB_URL=...
#   DEFAULT_AI_PROVIDER=...
#   OPENAI_API_KEY=...（或其他提供商的 Key）
```

### 构建并启动

```bash
docker compose up -d
```

**可选 build 参数**（国内网络加速 apt 下载）：

```env
# 在 .env 中添加（按实际网络情况选择）：
APT_DEBIAN_URL=http://mirrors.aliyun.com/debian
APT_SECURITY_URL=http://mirrors.aliyun.com/debian-security
```

### 容器数据持久化

`docker-compose.yml` 默认挂载以下 Volume：

| Volume | 容器路径 | 说明 |
|---|---|---|
| `landppt_data` | `/app/data` | 应用数据 |
| `landppt_uploads` | `/app/uploads` | 上传文件 |
| `landppt_cache` | `/app/temp` | 临时缓存 |
| `landppt_lib` | `/app/lib` | Apryse SDK（避免重复下载） |

`.env` 文件通过 `-v ./.env:/app/.env` 挂载进容器。

### 常用 Docker 命令

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f landppt

# 重启服务
docker compose restart landppt

# 停止并移除容器（数据 Volume 保留）
docker compose down

# 停止并移除容器 + 数据（危险！）
docker compose down -v
```

---

## 7. 验证部署

服务启动后，通过以下方式验证：

### 健康检查

```bash
curl http://localhost:8000/v1/health
```

正常返回：

```json
{
  "status": "healthy",
  "version": "v1",
  "ai_provider": "openai",
  "task_stats": { ... }
}
```

### 查看 Swagger 文档

浏览器打开：`http://localhost:8000/docs`

### 快速冒烟测试

```bash
# 提交一个生成任务
curl -X POST http://localhost:8000/v1/presentations \
  -H "Content-Type: application/json" \
  -d '{"topic": "测试", "scenario": "general"}'

# 预期返回 202 + job_id + project_id
```

---

## 8. 可选功能配置

### MongoDB 索引与模板初始化

应用**首次启动时自动完成**以下初始化，无需手动操作：

- 创建 MongoDB 集合和索引
- 将 `template_examples/` 目录下的内置 PPT 模板导入数据库

多进程（`WORKERS > 1`）场景下，通过文件锁保证初始化只执行一次。

### 多进程部署说明

- `WORKERS > 1` 时自动关闭 `RELOAD`（两者不兼容）
- 使用 Valkey 缓存时，多进程间缓存可共享；使用内存缓存时各进程独立
- 后台任务（PPT 生成）由各 worker 独立执行，不跨进程调度

### Nginx 反向代理示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # PPT 生成可能耗时较长，适当延长超时
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    client_max_body_size 20M;   # 允许上传较大文件

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 9. 注意事项

### MongoDB 连接失败

如果 MongoDB 无法连接，服务**启动会直接报错**，不会静默忽略。请确保：
- MongoDB 服务已启动（`mongod` 进程存在）
- `MONGODB_URL` 地址、端口、认证信息正确
- 服务器防火墙允许 27017 端口

### AI 提供商选择建议

| 场景 | 推荐 |
|---|---|
| 国内服务器，预算有限 | OpenAI 兼容中转接口（修改 `OPENAI_BASE_URL`）|
| 追求生成质量 | Claude 3.5 Sonnet / GPT-4o |
| 私有化部署，数据不出境 | Ollama + 本地模型 |
| 已有 Azure 账号 | Azure OpenAI |

### LLM 超时调优

PPT 生成包含多次 LLM 调用，默认超时 600 秒。若生成大型 PPT（20+ 页）或模型响应较慢，可适当提高：

```env
LLM_TIMEOUT_SECONDS=900
```

### 存储说明

- 项目**仅使用 MongoDB** 一种持久化存储，无 PostgreSQL / SQLite 依赖
- Valkey 仅用于缓存加速，不存储业务数据，可选
- 生成的 PPT HTML 直接存储在 MongoDB 项目文档中，通过 API 按需读取

### 旧版 docker-compose.yml 警告

仓库中的 `docker-compose.yml` 包含旧版 PostgreSQL 和 Valkey 的配置段，可以忽略 PostgreSQL 相关部分，以 `.env` 中的 `MONGODB_URL` 为准。后续版本会清理此文件。
