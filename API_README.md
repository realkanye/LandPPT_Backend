# LandPPT API - Pure API Mode (No Authentication)

## 📋 Overview

LandPPT纯API模式提供完整的PPT生成功能，无需认证即可使用。基于FastAPI构建，支持异步处理和流式响应。

**核心功能：**
- 从主题生成完整PPT
- 从文档文件生成PPT
- 7种场景模板
- AI智能大纲生成
- 网络研究内容增强
- 多格式导出（HTML、PDF、PPTX）
- 幻灯片编辑和重新生成
- AI图片生成和匹配

---

## 🚀 快速开始

### 1. 配置环境变量

```bash
cp .env.api .env
# 编辑 .env 文件，配置你的 AI API Key
```

### 2. 启动API服务器

```bash
# 使用 uv (推荐)
uv sync
uv run python run_api.py

# 或使用传统 pip
pip install -e .
python run_api.py
```

### 3. 访问API文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

---

## 📡 API 端点概览

| 分类 | 端点 | 方法 | 说明 |
|------|------|------|------|
| **系统** | `/health` | GET | 健康检查 |
| **大纲** | `/outline/generate` | POST | 生成PPT大纲 |
| **文件** | `/upload` | POST | 上传并处理文件 |
| **项目** | `/projects` | POST | 创建PPT项目 |
| **项目** | `/projects` | GET | 列出所有项目 |
| **项目** | `/projects/{id}` | GET | 获取项目详情 |
| **项目** | `/projects/{id}` | DELETE | 删除项目 |
| **项目** | `/projects/{id}/todo` | GET | 获取工作流进度 |
| **幻灯片** | `/projects/{id}/generate-slides` | POST | 生成完整幻灯片 |
| **幻灯片** | `/projects/{id}/slides/{index}/regenerate` | POST | 重新生成单张幻灯片 |
| **模板** | `/scenarios` | GET | 获取可用场景列表 |
| **模板** | `/projects/{id}/select-template` | POST | 选择模板 |
| **导出** | `/projects/{id}/export/html` | GET | 导出HTML |
| **导出** | `/projects/{id}/export/pdf` | POST | 导出PDF |
| **导出** | `/projects/{id}/export/pptx` | POST | 导出PPTX |
| **研究** | `/research/status` | GET | 研究服务状态 |
| **研究** | `/research/conduct` | POST | 进行网络研究 |
| **快速** | `/generate` | POST | 一键生成完整PPT |

---

## 💡 使用示例

### 示例 1: 一键生成完整PPT

```bash
curl -X POST "http://localhost:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "technology",
    "topic": "人工智能在医疗领域的应用",
    "requirements": "包含10页内容，重点介绍最新进展",
    "language": "zh"
  }'
```

### 示例 2: 分步工作流

#### 步骤1: 创建项目
```bash
curl -X POST "http://localhost:8000/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "business",
    "topic": "2024年Q2季度产品规划",
    "requirements": "重点介绍新产品线和市场策略"
  }'
```

#### 步骤2: 查看工作流进度
```bash
curl "http://localhost:8000/projects/{project_id}/todo"
```

#### 步骤3: 从指定阶段继续
```bash
curl -X POST "http://localhost:8000/projects/{project_id}/continue-from-stage?stage_index=2"
```

#### 步骤4: 导出PPTX
```bash
curl -X POST "http://localhost:8000/projects/{project_id}/export/pptx" \
  --output presentation.pptx
```

### 示例 3: 从文件生成PPT

```bash
# 第一步：上传文件
curl -X POST "http://localhost:8000/upload" \
  -F "file=@document.pdf"

# 第二步：从文件内容生成大纲
curl -X POST "http://localhost:8000/files/generate-outline" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "temp/uploads/document.pdf",
    "filename": "document.pdf",
    "topic": "从文档提取主题",
    "scenario": "analysis"
  }'
```

---

## 📝 请求模型详解

### PPTGenerationRequest

```typescript
{
  scenario: string;           // 场景类型: general, tourism, education, analysis, history, technology, business
  topic: string;              // PPT主题
  requirements?: string;      // 额外要求说明
  network_mode?: boolean;     // 是否启用网络研究模式
  language?: string;          // 语言: zh, en
  uploaded_content?: string;  // 上传文件的内容
  target_audience?: string;   // 目标受众
  ppt_style?: string;         // 风格: general, conference, custom
  custom_style_prompt?: string; // 自定义风格提示
  use_file_content?: boolean; // 是否使用文件内容
  file_processing_mode?: string; // 文件处理模式: markitdown, magic_pdf
}
```

---

## 🔧 测试脚本

项目包含完整的测试脚本 `test_api.py`：

```bash
# 运行完整API测试
python test_api.py

# 运行特定测试
python test_api.py test_health
python test_api.py test_outline
python test_api.py test_full_generation
```

---

## 📊 工作流阶段

LandPPT采用分阶段工作流设计：

| 阶段索引 | 阶段名称 | 说明 |
|----------|----------|------|
| 0 | requirements_confirm | 需求确认 |
| 1 | research | 网络研究 (可选) |
| 2 | outline_generation | 大纲生成 |
| 3 | outline_validate | 大纲验证 |
| 4 | creative_design | 创意设计 |
| 5 | template_selection | 模板选择 |
| 6 | slide_generation | 幻灯片生成 |
| 7 | layout_repair | 布局修复 |
| 8 | speech_script | 演讲稿生成 |
| 9 | export | 导出处理 |

---

## 🔒 安全说明

⚠️ **API模式无认证，仅限内部网络使用！**

- 不要直接暴露在公网
- 建议配置网络访问控制列表（ACL）
- API Key等敏感信息通过环境变量配置
- 考虑在生产环境中添加API密钥认证中间件

---

## 🐛 故障排查

### 问题: AI调用失败
**解决:** 检查 `.env` 中的API Key配置是否正确

### 问题: 中文乱码
**解决:** 确保系统字体已安装，检查HTML导出的字符编码

### 问题: PDF导出失败
**解决:** 确保Playwright浏览器已安装，运行 `playwright install chromium`

### 问题: 并行生成缓慢
**解决:** 调整 `PARALLEL_SLIDES_COUNT` 配置，根据服务器性能优化

---

## 📞 技术支持

如遇问题，请检查：
1. 服务日志输出
2. `/health` 端点返回的状态
3. 环境变量配置是否正确
