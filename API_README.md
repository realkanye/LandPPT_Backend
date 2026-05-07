# LandPPT API 使用指南

本文档说明如何通过 API 接口制作 PPT，包括接口调用方式、请求参数、返回格式以及完整的内部处理流程。

> 服务无需认证，开箱即用。启动配置请参阅 [DEPLOYMENT.md](./DEPLOYMENT.md)。

---

## 目录

1. [服务基础信息](#1-服务基础信息)
2. [制作 PPT —— 完整流程](#2-制作-ppt--完整流程)
3. [接口详细说明](#3-接口详细说明)
   - [提交生成任务](#31-post-v1presentations--提交生成任务)
   - [查询任务状态](#32-get-v1jobsjob_id--查询任务状态)
   - [下载 HTML 结果](#33-get-v1presentationsproject_iddownload--下载-html)
   - [上传源文档](#34-post-v1filesupload--上传源文档可选)
   - [导出 PDF / PPTX](#35-post-v1presentationsproject_idexports--导出-pdfpptx可选)
   - [下载导出文件](#36-get-v1jobsjob_iddownload--下载导出文件)
4. [其他辅助接口](#4-其他辅助接口)
5. [内部处理流程详解](#5-内部处理流程详解)
6. [完整 curl 示例](#6-完整-curl-示例)
7. [常见问题](#7-常见问题)

---

## 1. 服务基础信息

| 项目 | 值 |
|---|---|
| 默认地址 | `http://localhost:8000` |
| API 前缀 | `/v1` |
| 认证方式 | 无（无需 Token） |
| 在线交互文档 | `http://localhost:8000/docs`（Swagger UI） |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |

---

## 2. 制作 PPT —— 完整流程

### 最简路径（纯文字生成）

```
① POST /v1/presentations          提交任务，立即返回 job_id + project_id
         ↓
② GET  /v1/jobs/{job_id}          每隔几秒轮询，直到 status = completed
         ↓
③ GET  /v1/presentations/{project_id}/download?format=html   下载 PPT HTML
```

### 基于文档生成 PPT

```
① POST /v1/files/upload            上传 DOCX / PDF / TXT / MD，获得 processed_content
         ↓
② POST /v1/presentations           请求体中填入 uploaded_content = processed_content
         ↓
③ GET  /v1/jobs/{job_id}           轮询至完成
         ↓
④ GET  /v1/presentations/{project_id}/download?format=html   下载
```

### 导出为 PDF 或 PPTX

```
在下载 HTML 之后，如需要 PDF / PPTX 格式：

① POST /v1/presentations/{project_id}/exports?format=pdf    提交导出任务
         ↓
② GET  /v1/jobs/{job_id}           轮询导出任务，直到 status = completed
         ↓
③ GET  /v1/jobs/{job_id}/download  下载文件
```

---

## 3. 接口详细说明

### 3.1 `POST /v1/presentations` — 提交生成任务

提交 PPT 生成任务，服务**立即返回** 202 Accepted，实际生成在后台异步执行。

**请求体（application/json）：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `topic` | string | **是** | — | PPT 主题，例如 `"人工智能在医疗领域的应用"` |
| `scenario` | string | 否 | `"general"` | 场景类型，见下方取值表 |
| `requirements` | string | 否 | — | 额外要求，例如 `"重点介绍诊断辅助和药物研发"` |
| `language` | string | 否 | `"zh"` | 语言：`zh`（中文）/ `en`（英文）|
| `target_audience` | string | 否 | — | 目标受众，例如 `"医疗行业从业者"` |
| `ppt_style` | string | 否 | `"general"` | 风格：`general` / `conference` / `custom` |
| `custom_style_prompt` | string | 否 | — | 自定义风格描述，仅 `ppt_style=custom` 时生效 |
| `network_mode` | boolean | 否 | `false` | 是否启用联网搜索以增强内容（需要配置搜索服务） |
| `uploaded_content` | string | 否 | — | 来自 `POST /v1/files/upload` 的 `processed_content` |

**`scenario` 取值：**

| 值 | 中文名 | 适用场景 |
|---|---|---|
| `general` | 通用 | 通用商务场景 |
| `tourism` | 旅游观光 | 旅游线路、景点介绍 |
| `education` | 儿童科普 | 教育培训、科普知识 |
| `analysis` | 深入分析 | 数据分析、研究报告 |
| `history` | 历史文化 | 历史事件、文化传承 |
| `technology` | 科技技术 | 技术介绍、产品发布 |
| `business` | 方案汇报 | 商业计划、项目汇报 |

**请求示例：**

```bash
curl -X POST http://localhost:8000/v1/presentations \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "人工智能在医疗领域的应用",
    "scenario": "technology",
    "requirements": "重点介绍诊断辅助和药物研发两个方向",
    "language": "zh",
    "target_audience": "医疗行业从业者",
    "ppt_style": "general",
    "network_mode": false
  }'
```

**返回（202 Accepted）：**

```json
{
  "job_id": "a1b2c3d4-...",
  "project_id": "e5f6g7h8-...",
  "status": "pending",
  "message": "任务已提交。GET /v1/jobs/{job_id} 轮询进度，完成后用 /v1/presentations/{project_id}/download 下载。"
}
```

---

### 3.2 `GET /v1/jobs/{job_id}` — 查询任务状态

**请求示例：**

```bash
curl http://localhost:8000/v1/jobs/a1b2c3d4-...
```

**返回：**

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "running",
  "progress": 55.0,
  "project_id": "e5f6g7h8-...",
  "error": null,
  "created_at": "2024-01-01T10:00:00",
  "updated_at": "2024-01-01T10:01:30"
}
```

**`status` 取值：**

| 值 | 说明 |
|---|---|
| `pending` | 任务已排队，等待执行 |
| `running` | 正在生成中 |
| `completed` | 生成完成，可下载 |
| `failed` | 生成失败，见 `error` 字段 |

> 建议轮询间隔：每 **3~5 秒**一次。PPT 生成通常耗时 30 秒到几分钟，取决于页数和 AI 响应速度。

---

### 3.3 `GET /v1/presentations/{project_id}/download` — 下载 HTML

任务完成后，下载生成的 PPT HTML 文件。

**请求示例：**

```bash
curl http://localhost:8000/v1/presentations/e5f6g7h8-.../download?format=html \
  -o my_presentation.html
```

| 参数 | 说明 |
|---|---|
| `format` | 当前仅支持 `html`（默认）。PDF / PPTX 请使用 `/exports` 接口 |

返回内容为完整 HTML，可直接用浏览器打开查看和演示。

---

### 3.4 `POST /v1/files/upload` — 上传源文档（可选）

上传一份已有文档，服务提取其文字内容，用于基于文档生成 PPT。

**支持格式：** `.docx` / `.pdf` / `.txt` / `.md`

**请求示例：**

```bash
curl -X POST http://localhost:8000/v1/files/upload \
  -F "file=@research_report.pdf"
```

**返回：**

```json
{
  "filename": "research_report.pdf",
  "size": 204800,
  "file_type": ".pdf",
  "processed_content": "（提取的文字内容...）",
  "message": "文件上传并处理成功，processed_content 可直接用于创建 PPT"
}
```

将 `processed_content` 的值填入 `POST /v1/presentations` 的 `uploaded_content` 字段即可。

---

### 3.5 `POST /v1/presentations/{project_id}/exports` — 导出 PDF/PPTX（可选）

PPT 生成完成后，提交一个导出任务将其转换为 PDF 或 PPTX。

**依赖说明：**
- **PDF**：需要 Playwright（Chromium）
- **PPTX**：**无外部 SDK 依赖**。项目内置的 SVG → DrawingML 转换器（基于 ppt-master 移植）直接从 `slides_svg` 生成原生可编辑形状，下载后用 PowerPoint / Keynote / WPS 打开即可逐个元素编辑文本和形状，与从头创建的 PPT 同等。

**请求示例：**

```bash
# 导出 PDF
curl -X POST "http://localhost:8000/v1/presentations/e5f6g7h8-.../exports?format=pdf"

# 导出 PPTX
curl -X POST "http://localhost:8000/v1/presentations/e5f6g7h8-.../exports?format=pptx"
```

**返回（202 Accepted）：**

```json
{
  "job_id": "export-job-id-...",
  "project_id": "e5f6g7h8-...",
  "format": "pdf",
  "status": "pending",
  "message": "导出任务已提交。GET /v1/jobs/{job_id} 轮询，完成后 GET /v1/jobs/{job_id}/download 下载。"
}
```

之后同样用 `GET /v1/jobs/{job_id}` 轮询，完成后用下方接口下载。

---

### 3.6 `GET /v1/jobs/{job_id}/download` — 下载导出文件

导出任务完成后（`status=completed`），下载 PDF 或 PPTX 文件。

```bash
curl http://localhost:8000/v1/jobs/export-job-id-.../download \
  -o presentation.pdf
```

> 文件下载后服务端临时文件会自动清理，请勿重复下载。

---

## 4. 其他辅助接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/v1/health` | 服务健康检查，返回状态和 AI 提供商信息 |
| `GET` | `/v1/scenarios` | 获取所有支持的场景列表及描述 |
| `GET` | `/v1/ai/providers` | 获取当前可用的 AI 提供商列表 |
| `GET` | `/v1/presentations` | 分页列出所有已创建的 PPT 项目 |
| `GET` | `/v1/presentations/{project_id}` | 查看单个 PPT 项目详情（含大纲） |
| `DELETE` | `/v1/presentations/{project_id}` | 删除 PPT 项目 |

---

## 5. 内部处理流程详解

了解内部流程有助于排查问题和理解性能瓶颈。

```
POST /v1/presentations
│
├─ [同步，毫秒级]
│   ├─ 在 MongoDB 创建 Project 记录
│   │   └─ 初始化三个阶段的 Todo Board：
│   │       ① requirements_confirmation（需求确认）
│   │       ② outline_generation（大纲生成）
│   │       ③ ppt_creation（PPT 生成）
│   └─ 将任务投入后台队列 → 返回 job_id + project_id
│
└─ [后台异步任务]
    │
    ├─ 阶段 0：需求确认
    │   ├─ 将请求参数（topic、scenario、language 等）存入 MongoDB
    │   └─ 标记 requirements_confirmation 阶段 → completed
    │
    ├─ 阶段 1：大纲生成（LLM 调用）
    │   ├─ 读取 confirmed_requirements，构造 Prompt
    │   ├─ 调用 AI（outline 角色）→ 返回 JSON 结构的大纲
    │   ├─ 解析 JSON，自动校验和修复结构
    │   ├─ 若设置了页数限制，自动扩展/压缩至目标范围
    │   ├─ 将 outline（title + slides[]）写入 MongoDB
    │   └─ 标记 outline_generation 阶段 → completed
    │
    ├─ 阶段 2：PPT 生成（LLM 调用，最耗时）
    │   ├─ 从 MongoDB 读取大纲
    │   ├─ 为每一页幻灯片：
    │   │   ├─ 调用 AI 按结构化 SVG 协议生成（文字是 <text>，形状是真实图元）
    │   │   ├─ 自动清理代码块包装、补齐 viewBox/xmlns
    │   │   └─ 失败页降级为带错误提示的兜底 SVG，不阻塞整体流程
    │   ├─ 将 slides_svg（List[str]）写入 MongoDB
    │   └─ 标记 ppt_creation 阶段 → completed
    │
    │   PPTX 导出阶段（按需，POST /exports?format=pptx 触发）：
    │   ├─ 从 MongoDB 读取 slides_svg
    │   ├─ 经 svg_to_pptx 转换为原生 DrawingML 形状
    │   └─ 输出可编辑 .pptx，所有文字/形状均可在 PPT 中直接修改
    │
    └─ 标记 project.status → completed
           ↑ 此时轮询接口返回 status=completed，可下载
```

---

## 6. 完整 curl 示例

### 场景一：纯文字生成 PPT

```bash
#!/bin/bash
BASE_URL="http://localhost:8000"

# 第一步：提交生成任务
echo ">>> 提交生成任务..."
RESPONSE=$(curl -s -X POST "$BASE_URL/v1/presentations" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "人工智能在医疗领域的应用",
    "scenario": "technology",
    "requirements": "重点介绍诊断辅助和药物研发",
    "language": "zh",
    "target_audience": "医疗行业从业者"
  }')

echo "响应: $RESPONSE"
JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
PROJECT_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['project_id'])")
echo "job_id=$JOB_ID  project_id=$PROJECT_ID"

# 第二步：轮询任务状态
echo ">>> 轮询任务状态（每5秒一次）..."
while true; do
  STATUS_RESP=$(curl -s "$BASE_URL/v1/jobs/$JOB_ID")
  STATUS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  PROGRESS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['progress'])")
  echo "  状态: $STATUS  进度: $PROGRESS%"
  if [ "$STATUS" = "completed" ]; then
    echo ">>> 生成完成！"
    break
  fi
  if [ "$STATUS" = "failed" ]; then
    ERROR=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))")
    echo ">>> 生成失败: $ERROR"
    exit 1
  fi
  sleep 5
done

# 第三步：下载 HTML
echo ">>> 下载 PPT HTML..."
curl -s "$BASE_URL/v1/presentations/$PROJECT_ID/download?format=html" \
  -o "output.html"
echo ">>> 已保存为 output.html"
```

---

### 场景二：基于文档生成 PPT

```bash
BASE_URL="http://localhost:8000"

# 第一步：上传文档
echo ">>> 上传文档..."
UPLOAD_RESP=$(curl -s -X POST "$BASE_URL/v1/files/upload" \
  -F "file=@your_document.pdf")

PROCESSED=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['processed_content'])")
echo "文档内容已提取（${#PROCESSED} 字符）"

# 第二步：提交生成（含文档内容）
RESPONSE=$(curl -s -X POST "$BASE_URL/v1/presentations" \
  -H "Content-Type: application/json" \
  -d "{
    \"topic\": \"基于上传文档的PPT\",
    \"scenario\": \"business\",
    \"language\": \"zh\",
    \"uploaded_content\": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$PROCESSED")
  }")

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
PROJECT_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['project_id'])")
echo "job_id=$JOB_ID  project_id=$PROJECT_ID"
# 后续轮询和下载同场景一
```

---

### 场景三：导出为 PDF

```bash
BASE_URL="http://localhost:8000"
PROJECT_ID="your-project-id"   # 来自场景一/二

# 提交 PDF 导出任务
EXPORT_RESP=$(curl -s -X POST "$BASE_URL/v1/presentations/$PROJECT_ID/exports?format=pdf")
EXPORT_JOB_ID=$(echo "$EXPORT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# 轮询导出任务
while true; do
  STATUS=$(curl -s "$BASE_URL/v1/jobs/$EXPORT_JOB_ID" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "导出状态: $STATUS"
  [ "$STATUS" = "completed" ] && break
  [ "$STATUS" = "failed" ]    && echo "导出失败！" && exit 1
  sleep 3
done

# 下载 PDF
curl -s "$BASE_URL/v1/jobs/$EXPORT_JOB_ID/download" -o "output.pdf"
echo ">>> 已保存为 output.pdf"
```

---

## 7. 常见问题

**Q：提交任务后 `status` 一直是 `pending`，不变 `running`？**

后台任务队列是顺序执行的。如果上一个任务耗时较长，当前任务会排队等待。通常数秒内会开始执行。

**Q：任务 `status=failed`，如何排查？**

查看返回的 `error` 字段，同时检查服务端日志。常见原因：
- AI 提供商 API Key 未配置或余额不足
- LLM 请求超时（网络问题）
- MongoDB 连接异常

**Q：生成的 PPT 有多少页？**

默认由 AI 根据主题复杂度自动决定（通常 8~20 页）。如需固定页数，可在 `requirements` 字段中说明，例如：`"请生成恰好12页的PPT"`。

**Q：`network_mode=true` 有什么效果？**

开启后，大纲生成阶段会先通过搜索引擎检索相关资料，将搜索结果作为上下文融入 Prompt，使生成内容更具时效性。需要在服务端配置搜索 API（如 Tavily）。

**Q：HTML 如何转为演示文稿使用？**

下载的 HTML 文件可以：
1. 直接用浏览器打开，按 `F11` 全屏演示
2. 通过 `POST /v1/presentations/{id}/exports?format=pdf` 导出为 PDF 后用任意 PDF 阅读器播放
3. 通过 `POST /v1/presentations/{id}/exports?format=pptx` 导出为**可编辑 PPTX**，在 PowerPoint / Keynote / WPS 中逐元素修改文字和形状（无需任何商业 SDK）

**Q：如何查看所有历史项目？**

```bash
curl "http://localhost:8000/v1/presentations?page=1&page_size=10"
```
