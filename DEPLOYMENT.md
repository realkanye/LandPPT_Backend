# LandPPT Backend — 部署指南

本文档让你（或 Claude Code）从零开始把项目部署起来，并通过 curl 验证功能可用。

> 接口调用细节请阅读 [API_README.md](./API_README.md)。

---

## 目录

1. [资源与环境要求](#1-资源与环境要求)
2. [一键部署（开发/测试环境）](#2-一键部署开发测试环境)
3. [详细步骤](#3-详细步骤)
4. [配置环境变量](#4-配置环境变量)
5. [启动服务](#5-启动服务)
6. [Docker 部署](#6-docker-部署)
7. [部署后验证（curl 冒烟测试）](#7-部署后验证curl-冒烟测试)
8. [生产环境建议](#8-生产环境建议)
9. [故障排查](#9-故障排查)

---

## 1. 资源与环境要求

### 1.1 软件依赖

| 组件 | 版本 | 是否必须 | 说明 |
|---|---|:---:|---|
| **Python** | 3.11 或 3.12 | ✅ | 低于 3.11 不支持 |
| **MongoDB** | 6.x / 7.x | ✅ | 唯一持久化存储 |
| **AI 提供商** | — | ✅ | 至少 1 个：OpenAI / Claude / Gemini / Azure / Ollama |
| **uv** | ≥ 0.4 | 推荐 | 包管理器，比 pip 快很多 |
| **git** | 任意 | ✅ | 拉取代码 |
| **Valkey / Redis** | 7.x+ | ❌ | 多 worker 分布式缓存，单 worker 可不配 |
| **Playwright Chromium** | 最新 | ❌ | 仅导出 PDF 用；导出 PPTX **不需要** |

> ✅ **无 PostgreSQL / SQLite 依赖。**
> ✅ **无 Apryse / Aspose 等商业 SDK 依赖**——可编辑 PPTX 由项目内置的 SVG → DrawingML 转换器（[ppt-master](https://github.com/hugohe3/ppt-master) MIT 协议代码）直接生成。

### 1.2 硬件资源（最低配置）

| 场景 | CPU | 内存 | 磁盘 | 备注 |
|---|---|---|---|---|
| 开发机 | 2 核 | 2 GB | 2 GB | 单 worker，本地 MongoDB |
| 小规模生产 | 2 核 | 4 GB | 5 GB | 2 workers + 远程 MongoDB Atlas |
| PDF 导出（Playwright） | +1 核 | +1 GB | +500 MB | Chromium 浏览器开销 |
| Docker 单机一体化 | 2 核 | 4 GB | 10 GB | LandPPT + MongoDB + Valkey 同机 |

### 1.3 网络要求

- 出站：能连到所选 AI 提供商的 API（或自建代理网关）
- 入站：开放 `PORT`（默认 `8000`）给 API 调用方
- 联网搜索（可选）：能连到 Tavily API 或自建 SearXNG

---

## 2. 一键部署（开发/测试环境）

适合本机开发或试跑。假设已有可用的 AI API Key。

```bash
# ---- 1) 拉代码 ----
git clone <your-repo-url> LandPPT_Backend && cd LandPPT_Backend

# ---- 2) 装依赖（推荐 uv，比 pip 快 10x）----
pip install uv
uv sync --no-dev

# ---- 3) 启动本地 MongoDB（任选一种）----
# 方式 A：Docker（推荐，最快）
docker run -d --name landppt-mongo -p 27017:27017 mongo:7
# 方式 B：系统包：sudo apt install mongodb 或 brew install mongodb-community
# 方式 C：用 MongoDB Atlas 云数据库（直接跳过此步，把 URL 填到 .env 即可）

# ---- 4) 配置环境变量 ----
cp .env.example .env
# 编辑 .env，至少填两项：
#   MONGODB_URL=mongodb://localhost:27017/landppt
#   OPENAI_API_KEY=sk-xxx     （或其他提供商的 Key + 把 DEFAULT_AI_PROVIDER 改一下）

# ---- 5) 启动服务 ----
source .venv/bin/activate     # uv sync 创建的虚拟环境
python run.py
# 看到 "Uvicorn running on http://0.0.0.0:8000" 就是成功了

# ---- 6) 验证（新开终端）----
bash scripts/smoke_test.sh
```

如果第 6 步全部通过，说明部署完成，可以开始按 [API_README.md](./API_README.md) 调用接口。

---

## 3. 详细步骤

### 3.1 拉取代码

```bash
git clone <your-repo-url> LandPPT_Backend
cd LandPPT_Backend
```

### 3.2 安装 Python 依赖

```bash
# 方式一（推荐）：uv
pip install uv
uv sync --no-dev --frozen

# 方式二：传统 pip
python -m venv .venv
source .venv/bin/activate         # Linux / macOS
# .venv\Scripts\activate          # Windows
pip install -e .
```

### 3.3 安装 MongoDB

如果你已经有 MongoDB 实例（本机/云/团队共享），跳过这一节。

#### 选项 A：Docker（推荐）

```bash
docker run -d --name landppt-mongo \
  -p 27017:27017 \
  -v landppt_mongo_data:/data/db \
  mongo:7
```

#### 选项 B：系统包

```bash
# Ubuntu / Debian
sudo apt install -y mongodb

# macOS
brew tap mongodb/brew
brew install mongodb-community@7.0
brew services start mongodb-community@7.0
```

#### 选项 C：MongoDB Atlas（无需本地装）

注册 https://www.mongodb.com/atlas，建一个免费集群，拿到连接串：
`mongodb+srv://user:pass@cluster.mongodb.net/landppt`

### 3.4（可选）安装 Playwright（仅当需要 PDF 导出）

```bash
source .venv/bin/activate
playwright install chromium
playwright install-deps chromium     # Linux 服务器需要这一步装系统库
```

不需要 PDF 导出可以跳过——HTML 预览和可编辑 PPTX 不依赖 Playwright。

---

## 4. 配置环境变量

```bash
cp .env.example .env
```

`.env.example` 里所有字段都有详细注释。**最少需要填两类**：

### 4.1 必填

```env
# 1) MongoDB 连接串
MONGODB_URL=mongodb://localhost:27017/landppt

# 2) 选一个 AI 提供商，填它的 Key（其他的留空）
DEFAULT_AI_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 4.2 常见可选项

```env
# 服务器
HOST=0.0.0.0
PORT=8000
WORKERS=2

# 联网搜索（请求时 network_mode=true 才生效）
TAVILY_API_KEY=tvly-your-key
RESEARCH_PROVIDER=tavily

# 多 worker 时启用 Valkey 共享缓存
CACHE_BACKEND=valkey
VALKEY_URL=valkey://localhost:6379

# 关闭公开 Swagger
LANDPPT_ENABLE_API_DOCS=false
```

### 4.3 各 AI 提供商配置

| 提供商 | 必填字段 | 说明 |
|---|---|---|
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | 国内中转改 `OPENAI_BASE_URL` 即可 |
| Anthropic | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL` | — |
| Google | `GOOGLE_API_KEY`, `GOOGLE_MODEL`, `GOOGLE_BASE_URL` | — |
| Azure | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `AZURE_OPENAI_API_VERSION` | `DEFAULT_AI_PROVIDER=azure_openai` |
| Ollama | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | 先 `ollama pull <model>` |

---

## 5. 启动服务

### 5.1 直接启动（开发）

```bash
source .venv/bin/activate
python run.py
```

### 5.2 uvicorn（精细控制）

```bash
PYTHONPATH=src uvicorn landppt.main_api:app \
  --host 0.0.0.0 --port 8000 --workers 2
```

### 5.3 后台运行（生产，nohup）

```bash
mkdir -p logs
nohup python run.py > logs/landppt.log 2>&1 &
echo $! > landppt.pid
tail -f logs/landppt.log

# 停止
kill $(cat landppt.pid)
```

### 5.4 systemd（生产，推荐）

```ini
# /etc/systemd/system/landppt.service
[Unit]
Description=LandPPT Backend
After=network.target

[Service]
Type=simple
User=app
WorkingDirectory=/opt/LandPPT_Backend
Environment="PATH=/opt/LandPPT_Backend/.venv/bin"
ExecStart=/opt/LandPPT_Backend/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now landppt
sudo journalctl -u landppt -f
```

---

## 6. Docker 部署

仓库自带 `Dockerfile` + `docker-compose.yml`。

### 6.1 docker compose（一体化）

```bash
cp .env.example .env
# 编辑 .env

docker compose up -d

# 查看日志
docker compose logs -f landppt

# 停止
docker compose down
```

### 6.2 仅构建镜像

```bash
docker build -t landppt-backend:latest .

docker run -d --name landppt \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/uploads:/app/uploads \
  landppt-backend:latest
```

### 6.3 国内 apt 镜像加速（可选）

`.env` 中追加：

```env
APT_DEBIAN_URL=http://mirrors.aliyun.com/debian
APT_SECURITY_URL=http://mirrors.aliyun.com/debian-security
```

---

## 7. 部署后验证（curl 冒烟测试）

最快的方法：跑仓库自带的脚本。

```bash
bash scripts/smoke_test.sh
```

它会依次：
1. 调 `GET /v1/health` 检查健康
2. 调 `GET /v1/scenarios` 列出场景
3. `POST /v1/presentations` 提交一个真实生成任务
4. 轮询 `GET /v1/jobs/{job_id}` 直到 `status=completed`
5. 下载 `GET /v1/presentations/{project_id}/download?format=html`
6. 提交 `POST /v1/presentations/{project_id}/exports?format=pptx`
7. 轮询导出任务，下载 `.pptx` 文件

输出三个文件到当前目录：
- `smoke_preview.html` —— 浏览器打开看效果
- `smoke_output.pptx` —— PowerPoint / Keynote / WPS 打开，逐元素可编辑

如果不想跑脚本，下面是手动逐条验证：

```bash
BASE=http://localhost:8000

# 1) 健康检查
curl -s "$BASE/v1/health"
#   期望: {"status":"healthy","version":"v1","ai_provider":"openai",...}

# 2) 提交生成任务
RESP=$(curl -s -X POST "$BASE/v1/presentations" \
  -H "Content-Type: application/json" \
  -d '{"topic":"人工智能在医疗领域的应用","scenario":"technology","language":"zh"}')
JOB=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
PROJ=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['project_id'])")

# 3) 轮询（每 5 秒）
while true; do
  S=$(curl -s "$BASE/v1/jobs/$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "status: $S"; [ "$S" = "completed" ] && break; [ "$S" = "failed" ] && exit 1; sleep 5
done

# 4) 下 HTML 预览
curl -s "$BASE/v1/presentations/$PROJ/download?format=html" -o preview.html

# 5) 提交 PPTX 导出
EXPJOB=$(curl -s -X POST "$BASE/v1/presentations/$PROJ/exports?format=pptx" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# 6) 轮询导出任务
while true; do
  S=$(curl -s "$BASE/v1/jobs/$EXPJOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "export: $S"; [ "$S" = "completed" ] && break; [ "$S" = "failed" ] && exit 1; sleep 3
done

# 7) 下 PPTX
curl -s "$BASE/v1/jobs/$EXPJOB/download" -o output.pptx
```

---

## 8. 生产环境建议

| 主题 | 建议 |
|---|---|
| 进程管理 | systemd 或 supervisor，崩溃自动重启 |
| 反向代理 | Nginx / Caddy（必配长超时，PPT 生成可能 1-3 分钟） |
| Worker 数 | 2~4，受内存和 LLM 配额制约 |
| 缓存 | `WORKERS > 1` 时**必须**配 Valkey/Redis，否则缓存不一致 |
| 日志 | 结构化日志写到文件，配合 logrotate |
| 监控 | 监控 `GET /v1/health`；监控 `GET /v1/jobs/{id}` 失败率 |
| 备份 | 备份 MongoDB（生成的 PPT 全部存在 `landppt.projects` 集合） |
| Swagger | 公网部署设 `LANDPPT_ENABLE_API_DOCS=false` 关闭 `/docs` |
| API 限流 | 在 Nginx 或 API 网关层做 |

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    client_max_body_size 50M;          # 上传源文档

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

## 9. 故障排查

### 9.1 启动时报错

| 报错 | 原因 | 解决 |
|---|---|---|
| `Failed to connect to MongoDB` | MongoDB 没启或地址错 | 检查 `MONGODB_URL`，本机可 `mongosh` 连一下 |
| `No module named 'landppt'` | 没装到当前 Python | 重新 `uv sync` 或 `pip install -e .` |
| `AttributeError: get_pymongo_collection` | beanie 版本太旧 | `pip install -U "beanie>=2.0"` |
| 没有任何日志输出 | `RELOAD=true` + `WORKERS>1` 冲突 | 二选一，不能同时 |

### 9.2 任务一直 `pending` 不变 `running`

后台任务队列是顺序的，前面有任务在跑就会等。看 `GET /v1/health` 的 `task_stats` 字段。

### 9.3 任务 `failed`

```bash
curl -s "$BASE/v1/jobs/$JOB" | python3 -m json.tool
```

`error` 字段会说明失败原因。常见：
- AI Key 无效 / 余额不足 / 限流
- LLM 请求超时（调高 `LLM_TIMEOUT_SECONDS`）
- 网络不通到 AI 提供商

### 9.4 PPTX 打开后是空白 / 元素错乱

打开服务端日志看有没有 `LLM did not produce a parseable SVG` 之类的告警。LLM 偶尔会输出格式不合规的 SVG，被服务端兜底为简单错误页。换一个更强的模型（比如 `OPENAI_MODEL=gpt-4o`）通常能解决。

### 9.5 PDF 导出失败

```
PDF generation service unavailable (Playwright not installed?)
```

执行：

```bash
playwright install chromium
playwright install-deps chromium     # Linux only
```

### 9.6 打开 `/docs` 是 404

`LANDPPT_ENABLE_API_DOCS=false` 已主动关闭 Swagger。改回 `true` 重启即可。

---

## 附录：相关文件

| 文件 | 说明 |
|---|---|
| `run.py` | 服务启动入口 |
| `pyproject.toml` | Python 依赖列表（uv/pip 都读这个） |
| `.env.example` | 环境变量模板 |
| `Dockerfile` / `docker-compose.yml` | 容器部署文件 |
| `scripts/smoke_test.sh` | 部署后冒烟测试脚本 |
| `src/landppt/services/svg_to_pptx/` | 移植的 ppt-master 转换器（MIT） |
| `template_examples/` | 启动时自动导入的内置 PPT 模板（25 个） |
