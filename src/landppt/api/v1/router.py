"""
v1 API router — assembles all sub-routers under /v1.
"""

from fastapi import APIRouter

from . import files, jobs, presentations
from ...core.config import ai_config
from ...services.background_tasks import get_task_manager

router = APIRouter(prefix="/v1")

router.include_router(presentations.router, prefix="/presentations", tags=["v1 / Presentations"])
router.include_router(jobs.router, prefix="/jobs", tags=["v1 / Jobs"])
router.include_router(files.router, prefix="/files", tags=["v1 / Files"])


@router.get("/scenarios", tags=["v1 / Meta"], summary="获取支持的 PPT 场景列表")
async def list_scenarios():
    return [
        {"id": "general",    "name": "通用",     "description": "适用于各种通用商务场景"},
        {"id": "tourism",    "name": "旅游观光", "description": "旅游线路策划、景点介绍"},
        {"id": "education",  "name": "儿童科普", "description": "教育培训、科普知识"},
        {"id": "analysis",   "name": "深入分析", "description": "数据分析、研究报告"},
        {"id": "history",    "name": "历史文化", "description": "历史事件、文化传承"},
        {"id": "technology", "name": "科技技术", "description": "技术介绍、产品发布"},
        {"id": "business",   "name": "方案汇报", "description": "商业计划、项目汇报"},
    ]


@router.get("/ai/providers", tags=["v1 / Meta"], summary="获取可用 AI 提供商")
async def list_ai_providers():
    all_providers = ai_config.get_available_providers()
    return {
        "default_provider": ai_config.default_ai_provider,
        "available_providers": all_providers,
        "provider_status": {
            p: ai_config.is_provider_available(p) for p in all_providers
        },
    }


@router.get("/health", tags=["v1 / Meta"], summary="健康检查")
async def health():
    task_manager = get_task_manager()
    return {
        "status": "healthy",
        "version": "v1",
        "ai_provider": ai_config.default_ai_provider,
        "task_stats": task_manager.get_task_stats(),
    }
