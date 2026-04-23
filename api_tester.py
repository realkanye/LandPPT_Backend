#!/usr/bin/env python3
"""
LandPPT API 完整测试脚本
包含所有核心API的调用示例和返回内容说明
"""

import requests
import json
from typing import Dict, Any

API_BASE = "http://localhost:8000"

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def print_response(data: Dict[str, Any], max_len: int = 1500):
    """格式化打印响应"""
    output = json.dumps(data, ensure_ascii=False, indent=2)
    if len(output) > max_len:
        print(output[:max_len] + f"\n... (截断，总长度 {len(output)} 字符)")
    else:
        print(output)

# ----------------------------------------------------------------------------
# 1. 健康检查
# ----------------------------------------------------------------------------
def test_health_check():
    print_section("1. 健康检查 - GET /health")

    print("\n📡 请求代码:")
    print('''
curl -X GET "http://localhost:8000/health"
''')

    response = requests.get(f"{API_BASE}/health")
    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    print("\n📝 字段说明:")
    print("  • status: 服务状态，正常为 'healthy'")
    print("  • service: 服务名称，固定为 'LandPPT API'")
    print("  • version: API版本号")
    print("  • api_mode: 运行模式，纯API模式为 'pure_api_no_auth'")
    print("  • ai_provider: 默认使用的AI提供商")
    print("  • available_providers: 可用的AI提供商列表")

    return data

# ----------------------------------------------------------------------------
# 2. 获取场景模板列表
# ----------------------------------------------------------------------------
def test_scenarios():
    print_section("2. 获取场景模板 - GET /scenarios")

    print("\n📡 请求代码:")
    print('''
curl -X GET "http://localhost:8000/scenarios"
''')

    response = requests.get(f"{API_BASE}/scenarios")
    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    print("\n📝 字段说明 (每个场景对象):")
    print("  • id: 场景ID，用于后续API调用")
    print("  • name: 场景名称（中文）")
    print("  • description: 场景描述")
    print("  • icon: 图标emoji")
    print("  • template_config.style: 模板风格")
    print("  • template_config.color_scheme: 配色方案")
    print("  • template_config.font_family: 字体族")

    print("\n🎨 可用场景清单:")
    for s in data:
        print(f"  {s['icon']} {s['id']} - {s['name']}: {s['description']}")

    return data

# ----------------------------------------------------------------------------
# 3. 获取AI提供商状态
# ----------------------------------------------------------------------------
def test_ai_providers():
    print_section("3. AI提供商状态 - GET /ai/providers")

    print("\n📡 请求代码:")
    print('''
curl -X GET "http://localhost:8000/ai/providers"
''')

    response = requests.get(f"{API_BASE}/ai/providers")
    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    print("\n📝 字段说明:")
    print("  • default_provider: 默认使用的AI提供商")
    print("  • available_providers: 所有可用的提供商列表")
    print("  • provider_status: 每个提供商的配置状态（True/False）")

    return data

# ----------------------------------------------------------------------------
# 4. 生成PPT大纲
# ----------------------------------------------------------------------------
def test_generate_outline():
    print_section("4. 生成PPT大纲 - POST /outline/generate")

    request_data = {
        "scenario": "technology",
        "topic": "AI大模型在企业数字化转型中的应用实践",
        "requirements": "包含背景介绍、技术架构、落地案例、ROI分析",
        "language": "zh",
        "target_audience": "企业IT决策者和技术负责人",
        "ppt_style": "general"
    }

    print("\n📡 请求代码:")
    print(f'''
curl -X POST "http://localhost:8000/outline/generate" \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(request_data, ensure_ascii=False)}'
''')

    print("⏳ 正在生成大纲（约10秒）...")

    response = requests.post(
        f"{API_BASE}/outline/generate",
        json=request_data,
        timeout=120
    )

    if response.status_code != 200:
        print(f"\n❌ 请求失败，状态码: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None

    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    outline = data.get("outline", {})
    slides = outline.get("slides", [])

    print("\n📝 字段说明:")
    print("  • success: 是否成功（布尔值）")
    print("  • outline.title: PPT标题")
    print("  • outline.slides: 幻灯片列表，每页包含:")
    print("    - page_number: 页码")
    print("    - title: 幻灯片标题")
    print("    - content_points: 内容要点列表")
    print("    - slide_type: 幻灯片类型 (title, content, agenda, conclusion, thankyou)")
    print("    - chart_config: 图表配置（如有）")
    print("    - description: 幻灯片描述")
    print("  • outline.metadata.scenario: 使用的场景")
    print("  • outline.metadata.language: 语言")
    print("  • outline.metadata.total_slides: 总页数")
    print("  • message: 描述信息")

    print(f"\n📊 生成的大纲概览:")
    print(f"  标题: {outline.get('title', 'N/A')}")
    print(f"  页数: {len(slides)} 页")
    print("\n  幻灯片结构:")
    for slide in slides:
        slide_type = slide.get('slide_type', slide.get('type', 'content'))
        print(f"    [{slide.get('page_number', '?'):2d}] {slide.get('title', 'N/A')} ({slide_type})")

    return data

# ----------------------------------------------------------------------------
# 5. 创建PPT项目
# ----------------------------------------------------------------------------
def test_create_project():
    print_section("5. 创建PPT项目 - POST /projects")

    request_data = {
        "scenario": "business",
        "topic": "2024年度数字化战略规划报告",
        "requirements": "面向公司高管，突出战略价值和落地路线",
        "language": "zh"
    }

    print("\n📡 请求代码:")
    print(f'''
curl -X POST "http://localhost:8000/projects" \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps(request_data, ensure_ascii=False)}'
''')

    response = requests.post(
        f"{API_BASE}/projects",
        json=request_data,
        timeout=60
    )

    if response.status_code != 200:
        print(f"\n❌ 请求失败，状态码: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None

    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    project_id = data.get('project_id')

    print("\n📝 字段说明:")
    print("  • project_id: 项目唯一ID，后续所有操作都需要此ID")
    print("  • title: 项目标题")
    print("  • scenario: 使用的场景")
    print("  • topic: 主题")
    print("  • status: 项目状态 (draft, in_progress, completed)")
    print("  • todo_board: 工作流看板，包含所有阶段状态")
    print("  • version: 版本号")
    print("  • created_at: 创建时间戳")
    print("  • updated_at: 更新时间戳")

    todo = data.get('todo_board', {})
    stages = todo.get('stages', [])
    print(f"\n📋 工作流阶段:")
    for stage in stages:
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌"
        }.get(stage.get('status'), "❓")
        print(f"  {status_icon} {stage.get('id')}: {stage.get('name')} - {stage.get('status')}")

    return project_id

# ----------------------------------------------------------------------------
# 6. 获取项目列表
# ----------------------------------------------------------------------------
def test_list_projects():
    print_section("6. 获取项目列表 - GET /projects?page=1&page_size=10")

    print("\n📡 请求代码:")
    print('''
curl -X GET "http://localhost:8000/projects?page=1&page_size=10"
''')

    response = requests.get(f"{API_BASE}/projects?page=1&page_size=10")
    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    print("\n📝 字段说明:")
    print("  • projects: 项目列表数组")
    print("  • total: 总项目数")
    print("  • page: 当前页码")
    print("  • page_size: 每页数量")

    projects = data.get('projects', [])
    print(f"\n📚 共 {data.get('total', 0)} 个项目，本页 {len(projects)} 个:")
    for p in projects[:5]:
        print(f"  • {p.get('project_id')[:12]}... | {p.get('title')} | {p.get('status')}")
    if len(projects) > 5:
        print(f"  ... 还有 {len(projects) - 5} 个项目")

    return data

# ----------------------------------------------------------------------------
# 7. 获取指定项目详情
# ----------------------------------------------------------------------------
def test_get_project(project_id: str):
    print_section(f"7. 获取项目详情 - GET /projects/{project_id}")

    print("\n📡 请求代码:")
    print(f'''
curl -X GET "http://localhost:8000/projects/{project_id}"
''')

    response = requests.get(f"{API_BASE}/projects/{project_id}")
    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    print("\n📝 字段说明:")
    print("  • project_id: 项目ID")
    print("  • title: 项目标题")
    print("  • status: 项目状态")
    print("  • outline: 大纲数据（如已生成）")
    print("  • slides_html: 完整幻灯片HTML（如已生成）")
    print("  • slides_data: 结构化幻灯片数据（如已生成）")
    print("  • todo_board: 工作流看板")
    print("  • version: 版本号")

    return data

# ----------------------------------------------------------------------------
# 8. 获取工作流看板
# ----------------------------------------------------------------------------
def test_get_todo_board(project_id: str):
    print_section(f"8. 获取工作流看板 - GET /projects/{project_id}/todo")

    print("\n📡 请求代码:")
    print(f'''
curl -X GET "http://localhost:8000/projects/{project_id}/todo"
''')

    response = requests.get(f"{API_BASE}/projects/{project_id}/todo")
    data = response.json()

    print("\n📤 返回内容:")
    print_response(data)

    print("\n📝 字段说明:")
    print("  • task_id: 任务ID（同项目ID）")
    print("  • title: 任务标题")
    print("  • stages: 阶段列表，每个阶段包含:")
    print("    - id: 阶段ID")
    print("    - name: 阶段名称")
    print("    - description: 阶段描述")
    print("    - status: 状态 (pending, running, completed, failed)")
    print("    - progress: 进度 (0.0 - 1.0)")
    print("    - result: 阶段执行结果（如有）")
    print("  • current_stage_index: 当前执行到的阶段索引")
    print("  • overall_progress: 整体进度")
    print("  • created_at, updated_at: 创建/更新时间戳")

    stages = data.get('stages', [])
    print(f"\n📊 当前进度:")
    for i, stage in enumerate(stages):
        status = stage.get('status', 'pending')
        icon = {
            "pending": "⬜",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌"
        }.get(status, "❓")
        progress = int(stage.get('progress', 0) * 100)
        print(f"  {icon} 阶段{i}: {stage.get('name')} - {status} ({progress}%)")

    overall = int(data.get('overall_progress', 0) * 100)
    print(f"\n  总体进度: {overall}%")

    return data

# ----------------------------------------------------------------------------
# 9. 导出HTML
# ----------------------------------------------------------------------------
def test_export_html(project_id: str):
    print_section(f"9. 导出PPT为HTML - GET /projects/{project_id}/export/html")

    print("\n📡 请求代码:")
    print(f'''
curl -X GET "http://localhost:8000/projects/{project_id}/export/html" \\
  -o presentation.html
''')

    response = requests.get(f"{API_BASE}/projects/{project_id}/export/html")

    if response.status_code == 200 and response.text.strip():
        print(f"\n✅ HTML导出成功！内容长度: {len(response.text)} 字符")
        print("\n  HTML预览 (前500字符):")
        preview = response.text[:500]
        preview = preview.replace('\n', '\n  ')
        print(f"  {preview}...")

        print("\n📝 说明:")
        print("  • 返回内容为完整的HTML字符串，可直接保存为.html文件")
        print("  • 包含所有幻灯片、样式、图片引用")
        print("  • 可直接在浏览器中打开查看效果")

        return response.text
    else:
        print("\n⚠️  HTML为空或项目尚未生成幻灯片")
        print("  请先生成幻灯片后再导出")
        return None

# ----------------------------------------------------------------------------
# 主执行函数
# ----------------------------------------------------------------------------
def run_all_tests():
    print("\n" + "#"*60)
    print("#" + " "*15 + "LandPPT API 完整测试" + " "*18 + "#")
    print("#"*60)

    # 基础测试
    test_health_check()
    test_scenarios()
    test_ai_providers()

    # 大纲生成
    test_generate_outline()

    # 项目流程
    project_id = test_create_project()
    test_list_projects()

    if project_id:
        test_get_project(project_id)
        test_get_todo_board(project_id)
        test_export_html(project_id)  # 此时应为空，因为还没生成幻灯片

    print("\n" + "="*60)
    print("  ✅ 所有测试完成！")
    print("="*60)

    print("\n" + "📌 下一步:")
    print("  1. 访问 http://localhost:8000/docs 查看交互式API文档")
    print("  2. 使用 'POST /projects/{id}/continue-from-stage' 从指定阶段继续工作流")
    print("  3. 使用 'POST /projects/{id}/generate-slides' 生成完整幻灯片")
    print("  4. 使用导出API获取HTML/PDF/PPTX文件")


if __name__ == "__main__":
    run_all_tests()
