# 🚀 LandPPT API 接口文档（中文版）

## 基础信息

| 项 | 值 |
|----|----|
| 服务地址 | `http://localhost:8080` |
| API前缀 | `/api` |
| 认证方式 | JWT Bearer Token |
| 在线文档 | `http://localhost:8080/docs` (Swagger UI) |
| OpenAPI JSON | `http://localhost:8080/openapi.json` |

---

## 🔐 认证方式

所有需要登录的接口必须在请求头中携带：
```
Authorization: Bearer <你的JWT令牌>
```

---

## 📋 接口目录

### 一、健康检查 & 系统信息

| 方法 | 路径 | 说明 | 是否需要认证 |
|------|------|------|-------------|
| GET | `/health` | 服务健康检查 | 否 |
| GET | `/api/health` | API健康检查 | 否 |
| GET | `/api/ai/providers` | 获取可用的AI提供商列表 | 否 |
| POST | `/api/ai/providers/{provider}/test` | 测试AI提供商连接 | 否 |

**示例：健康检查**
```http
GET http://localhost:8080/health
```

**响应：**
```json
{
  "status": "healthy",
  "service": "LandPPT API",
  "version": "0.1.0"
}
```

---

### 二、用户认证接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 用户登录，获取JWT令牌 |
| POST | `/auth/logout` | 用户登出 |
| GET | `/auth/me` | 获取当前用户信息 |
| PUT | `/auth/profile` | 更新用户资料 |
| PUT | `/auth/password` | 修改密码 |

**示例：用户注册**
```http
POST http://localhost:8080/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "你的密码",
  "name": "用户名"
}
```

**示例：用户登录**
```http
POST http://localhost:8080/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "你的密码"
}
```

**响应：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "用户名"
  }
}
```

---

### 三、项目管理（PPT生成核心）

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|---------|
| POST | `/api/projects` | 创建新的PPT项目 | ✅ |
| GET | `/api/projects` | 获取用户的项目列表 | ✅ |
| GET | `/api/projects/{project_id}` | 获取项目详情 | ✅ |
| GET | `/api/projects/{project_id}/todo` | 获取生成进度（看板） | ✅ |
| PUT | `/api/projects/{project_id}/stages/{stage_id}` | 更新阶段状态 | ✅ |
| POST | `/api/projects/{project_id}/continue-from-stage` | 从指定阶段继续生成 | ✅ |
| DELETE | `/api/projects/{project_id}` | 删除项目 | ✅ |
| POST | `/api/projects/{project_id}/archive` | 归档项目 | ✅ |
| GET | `/api/projects/{project_id}/versions` | 获取项目版本历史 | ✅ |
| POST | `/api/projects/{project_id}/versions/{version}/restore` | 恢复到指定版本 | ✅ |
| POST | `/api/projects/{project_id}/slides/{slide_index}/lock` | 锁定幻灯片（防止重新生成） | ✅ |
| POST | `/api/projects/{project_id}/slides/{slide_index}/unlock` | 解锁幻灯片 | ✅ |
| POST | `/api/projects/{project_id}/select-template` | 为项目选择全局模板 | ✅ |
| GET | `/api/projects/{project_id}/selected-template` | 获取项目已选模板 | ✅ |

**示例：根据主题创建新项目**
```http
POST http://localhost:8080/api/projects
Content-Type: application/json
Authorization: Bearer <令牌>

{
  "scenario": "technology",
  "topic": "人工智能发展趋势",
  "requirements": "介绍最新技术发展、应用场景、未来展望",
  "network_mode": false,
  "language": "zh",
  "ppt_style": "general",
  "target_audience": "专业技术人员",
  "custom_style_prompt": null
}
```

**请求参数说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `scenario` | string | ✅ | PPT场景：`general`通用, `tourism`旅游, `education`教育, `analysis`分析, `history`历史, `technology`科技, `business`商务 |
| `topic` | string | ✅ | PPT主题 |
| `requirements` | string | ❌ | 额外生成要求 |
| `network_mode` | boolean | ❌ | 开启网络搜索增强内容，默认false |
| `language` | string | ❌ | 生成语言，默认"zh" |
| `ppt_style` | string | ❌ | PPT风格："general"通用, "conference"会议, "custom"自定义，默认"general" |
| `target_audience` | string | ❌ | 目标受众描述 |
| `custom_style_prompt` | string | ❌ | 自定义风格提示（当ppt_style="custom"时使用） |
| `uploaded_content` | string | ❌ | 上传文件提取的内容 |
| `user_id` | int | ❌ | 用户ID（通常由服务器设置） |

**响应：**
```json
{
  "project_id": "uuid-字符串",
  "title": "人工智能发展趋势",
  "scenario": "technology",
  "topic": "人工智能发展趋势",
  "status": "draft",
  "outline": { /* PPT大纲结构 */ },
  "slides_html": "/* 完整PPT的HTML */",
  "slides_data": [ /* 单页幻灯片数据数组 */ ],
  "created_at": "时间戳"
}
```

**示例：获取生成进度**
```http
GET http://localhost:8080/api/projects/{project_id}/todo
Authorization: Bearer <令牌>
```

**响应：**
```json
{
  "task_id": "uuid",
  "title": "生成PPT: 人工智能发展趋势",
  "current_stage_index": 1,
  "overall_progress": 35.5,
  "stages": [
    {
      "id": "topic_analysis",
      "name": "主题分析",
      "status": "completed",
      "progress": 100.0
    },
    {
      "id": "outline_generation",
      "name": "生成大纲",
      "status": "running",
      "progress": 50.0
    }
  ]
}
```

**示例：为项目选择模板**
```http
POST http://localhost:8080/api/projects/{project_id}/select-template
Content-Type: application/json
Authorization: Bearer <令牌>

{
  "project_id": "项目ID",
  "selected_template_id": 2,
  "template_mode": "selected"
}
```

**响应：**
```json
{
  "success": true,
  "message": "模板选择成功",
  "selected_template": {
    "id": 2,
    "template_name": "Toy风",
    "description": "可爱玩具风格模板",
    "html_template": "...",
    "tags": ["toy", "cute", "education"]
  }
}
```

---

### 四、全局母版模板管理

接口前缀：`/api/global-master-templates`

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|---------|
| GET | `/` | 获取所有模板（分页） | ✅ |
| GET | `/{template_id}` | 根据ID获取模板详情 | ✅ |
| GET | `/default/template` | 获取默认模板 | ✅ |
| POST | `/` | 创建新模板 | ✅ |
| PUT | `/{template_id}` | 更新模板 | ✅ |
| DELETE | `/{template_id}` | 删除模板 | ✅ |
| POST | `/{template_id}/set-default` | 设为默认模板 | ✅ |
| POST | `/generate` | 用AI生成新模板 | ✅ |
| POST | `/save-generated` | 保存AI生成的模板 | ✅ |
| POST | `/adjust-template` | 调整现有模板（支持流式） | ✅ |
| POST | `/select` | 选择模板用于生成 | ✅ |
| POST | `/{template_id}/duplicate` | 复制模板 | ✅ |
| GET | `/{template_id}/preview` | 获取模板预览 | ✅ |

**示例：获取模板列表**
```http
GET http://localhost:8080/api/global-master-templates?page=1&page_size=20&active_only=true
Authorization: Bearer <令牌>
```

**响应：**
```json
{
  "templates": [
    {
      "id": 1,
      "template_name": "简约商务",
      "description": "简约商务风格模板",
      "tags": ["business", "simple"],
      "preview_image": "预览图片URL",
      "is_default": true
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 29,
    "total_pages": 2
  }
}
```

**示例：AI生成新模板**
```http
POST http://localhost:8080/api/global-master-templates/generate
Content-Type: application/json
Authorization: Bearer <令牌>

{
  "prompt": "生成一个可爱的儿童教育风格PPT模板",
  "template_name": "可爱教育模板",
  "description": "适合儿童科普内容的可爱模板",
  "tags": ["education", "cute", "toy"],
  "generation_mode": "free"
}
```

**响应：**
```json
{
  "success": true,
  "message": "模板生成完成",
  "data": {
    "html_template": "<!DOCTYPE html>...",
    "template_name": "可爱教育模板"
  }
}
```

---

### 五、文件上传 & 从文件生成PPT

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|---------|
| POST | `/api/upload` | 上传并处理单个文件 | ✅ |
| GET | `/api/upload/formats` | 获取支持的文件格式 | ✅ |
| POST | `/api/upload/create-project` | 上传文件并直接创建项目 | ✅ |
| POST | `/api/upload/analyze` | 分析上传文件并建议PPT结构 | ✅ |
| POST | `/api/files/generate-outline` | 从已有文件生成大纲 | ✅ |
| POST | `/api/files/upload-and-generate-outline` | 上传多个文件并生成大纲 | ✅ |

**支持的文件格式**：`.docx`、`.pdf`、`.txt`、`.md`

**示例：上传多个文件并生成大纲**
```http
POST http://localhost:8080/api/files/upload-and-generate-outline
Content-Type: multipart/form-data
Authorization: Bearer <令牌>

--boundary
Content-Disposition: form-data; name="files"; filename="document.pdf"
<... 文件内容 ...>

--boundary
Content-Disposition: form-data; name="files"; filename="notes.md"
<... 文件内容 ...>

--boundary
Content-Disposition: form-data; name="topic"
季度业务总结报告

--boundary
Content-Disposition: form-data; name="scenario"
business

--boundary
Content-Disposition: form-data; name="page_count_mode"
ai_decide

--boundary
Content-Disposition: form-data; name="min_pages"
8

--boundary
Content-Disposition: form-data; name="max_pages"
15

--boundary
Content-Disposition: form-data; name="language"
zh

--boundary
Content-Disposition: form-data; name="network_mode"
true
--boundary--
```

**响应：**
```json
{
  "success": true,
  "outline": {
    "title": "季度业务总结报告",
    "slides": [
      {
        "title": "封面",
        "content": "季度业务总结报告\n- 第三季度 2024"
      }
    ],
    "metadata": {
      "source_files": ["document.pdf", "notes.md"],
      "files_count": 2,
      "network_mode": true,
      "search_topic": "季度业务总结报告"
    }
  },
  "message": "大纲生成完成"
}
```

---

### 六、深度调研

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|---------|
| GET | `/api/research/status` | 获取调研服务状态 | ✅ |
| POST | `/api/research/conduct` | 对主题进行深度调研 | ✅ |
| GET | `/api/research/reports` | 获取已保存的调研报告列表 | ✅ |
| DELETE | `/api/research/reports/{filename}` | 删除调研报告 | ✅ |
| GET | `/api/research/enhanced/status` | 获取增强调研状态 | ✅ |
| POST | `/api/research/enhanced/conduct` | 执行增强深度调研 | ✅ |
| GET | `/api/research/enhanced/providers` | 获取可用的调研提供商 | ✅ |

**示例：执行增强调研**
```http
POST http://localhost:8080/api/research/enhanced/conduct?topic=大模型推理优化&language=zh
Authorization: Bearer <令牌>
```

**响应：**
```json
{
  "success": true,
  "message": "Enhanced research completed",
  "report": {
    "topic": "大模型推理优化",
    "language": "zh",
    "executive_summary": "本文总结了...",
    "key_findings": [...],
    "sources": [...],
    "total_duration": 125.5,
    "steps_count": 5
  }
}
```

---

### 七、图片服务

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|---------|
| GET | `/api/images` | 获取用户图片列表 | ✅ |
| POST | `/api/images/upload` | 上传图片 | ✅ |
| GET | `/api/images/{id}` | 根据ID获取图片 | ✅ |
| DELETE | `/api/images/{id}` | 删除图片 | ✅ |
| POST | `/api/images/generate` | 用AI生成图片 | ✅ |
| POST | `/api/images/suggest` | 为PPT幻灯片推荐图片 | ✅ |

---

### 八、配置 & 缓存

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|---------|
| GET | `/api/config` | 获取系统配置 | ✅ |
| PUT | `/api/config` | 更新系统配置（管理员） | ✅ |
| GET | `/api/cache/stats` | 获取缓存统计 | ✅ |
| POST | `/api/cache/cleanup` | 清理过期缓存 | ✅ |

---

### 九、OpenAI 兼容接口

接口前缀：`/v1`

完全兼容OpenAI API，可以直接使用OpenAI SDK：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat/completions` | 聊天补全 |
| POST | `/v1/completions` | 文本补全 |
| GET | `/v1/models` | 获取可用模型列表 |

**Python SDK使用示例：**
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://你的服务器地址:8080/v1",
    api_key="你的API密钥"  # 或者你的JWT令牌
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "你是一个有用的助手。"},
        {"role": "user", "content": "你好！"}
    ]
)

print(response.choices[0].message.content)
```

---

## 📊 PPT场景说明

| 场景ID | 名称 | 说明 |
|--------|------|------|
| `general` | 通用 | 适用于各种通用场景 |
| `tourism` | 旅游观光 | 旅游线路、景点介绍 |
| `education` | 儿童科普 | 教育培训、科普知识 |
| `analysis` | 深入分析 | 数据分析、研究报告 |
| `history` | 历史文化 | 历史事件、文化传承 |
| `technology` | 科技技术 | 技术介绍、产品发布 |
| `business` | 方案汇报 | 商业计划、项目汇报 |

---

## 🌐 前端页面路由

除了API接口，系统还提供完整的Web界面：

| 路径 | 页面说明 |
|------|---------|
| `/` | 首页（重定向到仪表盘） |
| `/dashboard` | 仪表盘 |
| `/projects` | 项目列表 |
| `/editor/{project_id}` | PPT编辑器 |
| `/templates` | 模板市场 |
| `/research` | 调研工作区 |
| `/settings` | 用户设置 |
| `/admin` | 管理员后台 |

---

## 🚀 服务状态

- ✅ **服务运行中**
- **访问地址**: `http://0.0.0.0:8080`
- **内置模板**: 29个（包含Toy风模板）
- **AI提供商**: SiliconFlow已配置完成
