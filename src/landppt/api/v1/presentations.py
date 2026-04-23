"""
Core PPT endpoints for the v1 API.

Workflow
--------
1. POST   /v1/presentations          → 提交异步生成任务，立即返回 job_id + project_id
2. GET    /v1/jobs/{job_id}          → 轮询任务状态（pending / running / completed / failed）
3. GET    /v1/presentations/{id}/download?format=html|pdf|pptx  → 下载最终文件
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from .models import (
    CreatePresentationRequest,
    JobResponse,
    PresentationDetail,
    PresentationListResponse,
    PresentationSummary,
)
from ...api.models import PPTGenerationRequest
from ...core.config import app_config
from ...services.background_tasks import get_task_manager
from ...services.service_instances import get_ppt_service_for_user

router = APIRouter()
logger = logging.getLogger(__name__)

_ANONYMOUS_USER_ID: int = app_config.anonymous_user_id

_WORKFLOW_STAGES = [
    "requirements_confirm",
    "outline_generation",
    "creative_design",
    "template_selection",
    "slide_generation",
    "layout_repair",
]


# ---------------------------------------------------------------------------
# Background generation function
# ---------------------------------------------------------------------------

async def _run_ppt_generation(project_id: str, confirmed_requirements: dict) -> dict:
    """
    Executes the full PPT generation pipeline.
    Runs as a background task via BackgroundTaskManager.submit_task().
    Returns a summary dict that is stored as task.result on completion.
    """
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)

    await ppt_service.confirm_requirements_and_update_workflow(
        project_id, confirmed_requirements
    )

    for stage_id in _WORKFLOW_STAGES:
        logger.info("project=%s stage=%s starting", project_id, stage_id)
        await ppt_service.start_workflow_from_stage(project_id, stage_id)
        logger.info("project=%s stage=%s done", project_id, stage_id)

    return {"project_id": project_id, "success": True}


# ---------------------------------------------------------------------------
# POST /v1/presentations
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=JobResponse,
    status_code=202,
    summary="创建 PPT（异步）",
    description=(
        "提交 PPT 生成任务。服务立即返回 202 Accepted 以及 job_id 和 project_id。"
        " 通过 GET /v1/jobs/{job_id} 轮询进度；"
        " 任务 status=completed 后通过 GET /v1/presentations/{project_id}/download 下载文件。"
    ),
)
async def create_presentation(request: CreatePresentationRequest):
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)

    ppt_request = PPTGenerationRequest(
        scenario=request.scenario,
        topic=request.topic,
        requirements=request.requirements,
        language=request.language,
        target_audience=request.target_audience,
        ppt_style=request.ppt_style,
        custom_style_prompt=request.custom_style_prompt,
        network_mode=request.network_mode,
        uploaded_content=request.uploaded_content,
        user_id=_ANONYMOUS_USER_ID,
    )

    try:
        project = await ppt_service.create_project_with_workflow(ppt_request)
    except Exception as exc:
        logger.exception("create_project_with_workflow failed")
        raise HTTPException(status_code=500, detail=f"创建项目失败: {exc}") from exc

    confirmed_requirements = {
        "topic": request.topic,
        "scenario": request.scenario,
        "requirements": request.requirements or "",
        "language": request.language or "zh",
        "target_audience": request.target_audience or "",
        "style": request.ppt_style or "general",
        "custom_style_prompt": request.custom_style_prompt or "",
    }

    task_manager = get_task_manager()
    job_id = task_manager.submit_task(
        "ppt_generation",
        _run_ppt_generation,
        project.project_id,
        confirmed_requirements,
        metadata={"project_id": project.project_id, "topic": request.topic},
    )

    logger.info("PPT job submitted job_id=%s project_id=%s", job_id, project.project_id)

    return JobResponse(
        job_id=job_id,
        project_id=project.project_id,
        status="pending",
        message="任务已提交。请用 GET /v1/jobs/{job_id} 轮询进度，完成后用 /v1/presentations/{project_id}/download 下载。",
    )


# ---------------------------------------------------------------------------
# GET /v1/presentations
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PresentationListResponse,
    summary="列出所有 PPT",
)
async def list_presentations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="按状态过滤: draft / in_progress / completed / archived"),
):
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    try:
        result = await ppt_service.project_manager.list_projects(
            page=page,
            page_size=page_size,
            status=status,
            user_id=_ANONYMOUS_USER_ID,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    summaries = []
    for p in result.projects:
        slides_count: Optional[int] = None
        if p.slides_data:
            slides_count = len(p.slides_data)
        summaries.append(
            PresentationSummary(
                project_id=p.project_id,
                title=p.title,
                topic=p.topic,
                scenario=p.scenario,
                status=p.status,
                slides_count=slides_count,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
        )

    return PresentationListResponse(
        presentations=summaries,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


# ---------------------------------------------------------------------------
# GET /v1/presentations/{project_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}",
    response_model=PresentationDetail,
    summary="获取 PPT 详情",
)
async def get_presentation(project_id: str):
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    project = await ppt_service.project_manager.get_project(
        project_id, user_id=_ANONYMOUS_USER_ID
    )
    if project is None:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    slides_count: Optional[int] = None
    if project.slides_data:
        slides_count = len(project.slides_data)

    return PresentationDetail(
        project_id=project.project_id,
        title=project.title,
        topic=project.topic,
        scenario=project.scenario,
        status=project.status,
        requirements=project.requirements,
        outline=project.outline,
        has_slides=bool(project.slides_html),
        slides_count=slides_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# ---------------------------------------------------------------------------
# DELETE /v1/presentations/{project_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/{project_id}",
    summary="删除 PPT",
)
async def delete_presentation(project_id: str):
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    try:
        success = await ppt_service.project_manager.delete_project(
            project_id=project_id, user_id=_ANONYMOUS_USER_ID
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not success:
        raise HTTPException(status_code=404, detail="PPT 不存在或删除失败")
    return {"success": True, "message": f"PPT {project_id} 已删除"}


# ---------------------------------------------------------------------------
# GET /v1/presentations/{project_id}/download
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}/download",
    summary="下载 PPT 文件",
    description=(
        "下载已生成的 PPT。"
        " `format` 参数: **html**（默认，直接返回 HTML 内容）/ **pdf** / **pptx**。"
        " 请确保任务状态为 completed 后再调用，否则返回 400。"
    ),
)
async def download_presentation(
    project_id: str,
    format: str = Query("html", description="导出格式: html / pdf / pptx"),
):
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    project = await ppt_service.project_manager.get_project(
        project_id, user_id=_ANONYMOUS_USER_ID
    )
    if project is None:
        raise HTTPException(status_code=404, detail="PPT 不存在")
    if not project.slides_html:
        raise HTTPException(
            status_code=400,
            detail="PPT 尚未生成完成，请先确认任务状态为 completed",
        )

    if format == "html":
        return HTMLResponse(content=project.slides_html)

    elif format == "pdf":
        try:
            pdf_path = await ppt_service.export_to_pdf(project_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF 导出失败: {exc}") from exc
        return FileResponse(
            path=pdf_path,
            filename=f"{project.title or project_id}.pdf",
            media_type="application/pdf",
        )

    elif format == "pptx":
        try:
            pptx_path = await ppt_service.export_to_pptx(project_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PPTX 导出失败: {exc}") from exc
        return FileResponse(
            path=pptx_path,
            filename=f"{project.title or project_id}.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的格式 '{format}'，支持: html / pdf / pptx",
        )
