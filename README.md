# LandPPT Backend

AI 驱动的 PPT 生成后端服务。给一个主题，AI 帮你生成大纲，再帮你画出**真正可编辑**的 PPTX 文件——不是图片，每一段文字、每一个形状都能在 PowerPoint / Keynote / WPS 中直接修改。

```
你的请求            后端流水线（全自动）           交付物
─────────  ────────────────────────────────  ──────────────────────
                                              ┌──→ 在线 HTML 预览
POST /v1/  →  LLM 生成大纲                    │      （浏览器演示）
presenta-     ↓                               │
tions     →  LLM 逐页生成结构化 SVG  →  ──────┼──→ 可编辑 PPTX
              ↓                               │      （PowerPoint）
              SVG → DrawingML 原生形状        │
                                              └──→ PDF
                                                     （Playwright）
```

---

## 文档导航

| 文档 | 用途 |
|---|---|
| **[DEPLOYMENT.md](./DEPLOYMENT.md)** | 部署指南：环境要求、安装、配置、启动、Docker。**第一次部署看这个。** |
| **[API_README.md](./API_README.md)** | API 使用指南：每个接口的参数、返回值、curl 示例、内部流程。**调用接口看这个。** |
| **[.env.example](./.env.example)** | 环境变量模板（注释中含字段说明）。 |

---

## 30 秒上手

```bash
# 1) 克隆
git clone <repo-url> LandPPT_Backend && cd LandPPT_Backend

# 2) 装依赖
pip install uv && uv sync --no-dev

# 3) 配置
cp .env.example .env
# 编辑 .env，至少填写 MONGODB_URL 和 OPENAI_API_KEY（或其他 AI 提供商）

# 4) 启动
python run.py

# 5) 提交一个 PPT 生成任务
curl -X POST http://localhost:8000/v1/presentations \
  -H "Content-Type: application/json" \
  -d '{"topic":"人工智能在医疗领域的应用","scenario":"technology"}'
```

完整冒烟测试见 `scripts/smoke_test.sh`。

---

## 项目能做什么

- ✅ **主题 → PPT**：给个主题（可选附加要求/受众/风格），自动产出 8~20 页 PPT
- ✅ **文档 → PPT**：上传 DOCX/PDF/TXT/MD，基于文档内容生成 PPT
- ✅ **可编辑 PPTX**：输出原生 DrawingML 形状，PowerPoint 中逐元素编辑
- ✅ **HTML 预览**：浏览器直接打开演示，键盘 ←/→ 翻页
- ✅ **PDF 导出**：标准 PDF 文件
- ✅ **多 AI 提供商**：OpenAI / Claude / Gemini / Azure OpenAI / Ollama，可分阶段指定不同模型
- ✅ **联网研究**（可选）：开 `network_mode=true` 启用 Tavily 搜索增强大纲

## 项目不做什么

- ❌ Web UI / 管理后台 —— 纯 API，无前端
- ❌ 用户认证 —— 接口免登录（适合放在内网或自建 API 网关后）
- ❌ 商业 SDK 依赖 —— 没有 Apryse / Aspose / 其他付费授权

---

## 技术栈

- **Python 3.11+** · FastAPI · uvicorn
- **MongoDB 6/7**（唯一持久层，通过 Beanie 2.x ODM）
- **Valkey / Redis 7+**（可选，分布式缓存）
- **AI**：OpenAI / Anthropic / Google / Azure / Ollama（任选）
- **PPTX 引擎**：从 [ppt-master](https://github.com/hugohe3/ppt-master) (MIT) 移植的 SVG → DrawingML 转换器，已内置在 `src/landppt/services/svg_to_pptx/`
- **PDF 引擎**：Playwright（Chromium，可选）

---

## 接口总览

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/v1/presentations` | 提交 PPT 生成任务，立即返回 `job_id` |
| `GET` | `/v1/jobs/{job_id}` | 轮询任务状态 |
| `GET` | `/v1/presentations/{id}/download?format=html` | 下载 HTML 预览 |
| `POST` | `/v1/presentations/{id}/exports?format=pptx\|pdf` | 提交 PPTX/PDF 导出任务 |
| `GET` | `/v1/jobs/{job_id}/download` | 下载导出的 PPTX/PDF 文件 |
| `POST` | `/v1/files/upload` | 上传 DOCX/PDF/TXT/MD 源文档 |
| `GET` | `/v1/health` · `/v1/scenarios` · `/v1/ai/providers` | 元信息接口 |

详见 [API_README.md](./API_README.md)。

---

## 协议

- 本仓库代码：Apache 2.0
- `src/landppt/services/svg_to_pptx/` 与 `services/svg_finalize/`：MIT，源自 [ppt-master](https://github.com/hugohe3/ppt-master)（Hugo He, 2025-2026）
