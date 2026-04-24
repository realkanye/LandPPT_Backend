"""
Core PPT endpoints for the v1 API.

Workflow — PPT creation
-----------------------
1. POST   /v1/presentations                    → 提交异步生成任务，立即返回 job_id + project_id
2. GET    /v1/jobs/{job_id}                    → 轮询任务状态（pending/running/completed/failed）
3. GET    /v1/presentations/{id}/download?format=html  → 下载 HTML（立即返回）

Workflow — PDF / PPTX export
-----------------------------
1. POST   /v1/presentations/{id}/exports?format=pdf   → 提交导出任务，返回 job_id
2. GET    /v1/jobs/{job_id}                            → 轮询导出状态
3. GET    /v1/jobs/{job_id}/download                   → 下载文件（status=completed 后有效）
"""

import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from starlette.background import BackgroundTask

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


# ---------------------------------------------------------------------------
# Background task functions (also imported by main_api.py for legacy routes)
# ---------------------------------------------------------------------------

async def _run_ppt_generation(project_id: str, confirmed_requirements: dict) -> dict:
    """Full PPT generation pipeline — runs as a BackgroundTaskManager task."""
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)

    await ppt_service.confirm_requirements_and_update_workflow(
        project_id, confirmed_requirements
    )

    # Reconstruct the request object that _execute_project_workflow needs.
    # The workflow reads confirmed_requirements from the DB (saved above), so
    # only the identity fields (user_id, topic, scenario) matter here.
    ppt_request = PPTGenerationRequest(
        scenario=confirmed_requirements.get("scenario", "general"),
        topic=confirmed_requirements.get("topic", ""),
        requirements=confirmed_requirements.get("requirements", ""),
        language=confirmed_requirements.get("language", "zh"),
        target_audience=confirmed_requirements.get("target_audience", ""),
        ppt_style=confirmed_requirements.get("style", "general"),
        custom_style_prompt=confirmed_requirements.get("custom_style_prompt", ""),
        user_id=_ANONYMOUS_USER_ID,
    )

    await ppt_service._execute_project_workflow(
        project_id, ppt_request, user_id=_ANONYMOUS_USER_ID
    )
    return {"project_id": project_id, "success": True}


async def _run_pdf_export(project_id: str, user_id: int) -> dict:
    """
    Export a completed presentation to PDF.
    Writes a NamedTemporaryFile and returns its path in the result dict.
    The file is NOT auto-deleted — the download endpoint serves then deletes it.
    Requires Playwright (pyppeteer) to be installed and functional.
    """
    # Lazy import to avoid loading web-layer modules at startup.
    from ...services.export_support import _generate_pdf_with_pyppeteer
    from ...services.pyppeteer_pdf_converter import get_pdf_converter

    ppt_service = get_ppt_service_for_user(user_id)
    project = await ppt_service.project_manager.get_project(project_id, user_id=user_id)
    if not project:
        return {"success": False, "error": f"Project {project_id} not found"}
    if not project.slides_data:
        return {"success": False, "error": "PPT slides not generated yet"}

    pdf_converter = get_pdf_converter()
    if not pdf_converter.is_available():
        return {"success": False, "error": "PDF generation service unavailable (Playwright not installed?)"}

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    temp_path = tmp.name

    success = await _generate_pdf_with_pyppeteer(project, temp_path, individual=False)
    if not success:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        return {"success": False, "error": "PDF generation failed"}

    filename = f"{project.title or project_id}.pdf"
    return {"success": True, "file_path": temp_path, "filename": filename, "media_type": "application/pdf"}


async def _run_pptx_export(project_id: str, user_id: int) -> dict:
    """
    Export a completed presentation to PPTX (PDF → Apryse conversion).
    Requires ENABLE_APRYSE_PPTX_EXPORT=true and a valid APRYSE_LICENSE_KEY.
    Returns the temp file path in the result dict.
    """
    from ...services.export_support import _generate_pdf_with_pyppeteer
    from ...services.pyppeteer_pdf_converter import get_pdf_converter
    from ...services.pdf_to_pptx_converter import get_pdf_to_pptx_converter

    ppt_service = get_ppt_service_for_user(user_id)
    project = await ppt_service.project_manager.get_project(project_id, user_id=user_id)
    if not project:
        return {"success": False, "error": f"Project {project_id} not found"}
    if not project.slides_data:
        return {"success": False, "error": "PPT slides not generated yet"}

    pdf_converter = get_pdf_converter()
    if not pdf_converter.is_available():
        return {"success": False, "error": "PDF generation service unavailable (Playwright not installed?)"}

    pptx_converter = get_pdf_to_pptx_converter()
    if not pptx_converter.is_available():
        return {
            "success": False,
            "error": "PPTX conversion unavailable. Set ENABLE_APRYSE_PPTX_EXPORT=true and configure APRYSE_LICENSE_KEY.",
        }

    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_pdf.close()
    tmp_pptx = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
    tmp_pptx.close()

    try:
        pdf_ok = await _generate_pdf_with_pyppeteer(project, tmp_pdf.name, individual=False)
        if not pdf_ok:
            return {"success": False, "error": "PDF generation failed"}

        ok, _result = await pptx_converter.convert_pdf_to_pptx_async(tmp_pdf.name, tmp_pptx.name)
        if not ok:
            return {"success": False, "error": "PDF → PPTX conversion failed"}

        filename = f"{project.title or project_id}.pptx"
        return {
            "success": True,
            "file_path": tmp_pptx.name,
            "filename": filename,
            "media_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
    finally:
        try:
            os.unlink(tmp_pdf.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# POST /v1/presentations
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=JobResponse,
    status_code=202,
    summary="创建 PPT（异步）",
    description=(
        "提交 PPT 生成任务。服务立即返回 202 Accepted 以及 `job_id` 和 `project_id`。\n\n"
        "通过 `GET /v1/jobs/{job_id}` 轮询进度；"
        " `status=completed` 后通过 `GET /v1/presentations/{project_id}/download?format=html` 下载。"
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
        message="任务已提交。GET /v1/jobs/{job_id} 轮询进度，完成后用 /v1/presentations/{project_id}/download 下载。",
    )


# ---------------------------------------------------------------------------
# GET /v1/presentations
# ---------------------------------------------------------------------------

@router.get("", response_model=PresentationListResponse, summary="列出所有 PPT")
async def list_presentations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="按状态过滤: draft/in_progress/completed/archived"),
):
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    try:
        result = await ppt_service.project_manager.list_projects(
            page=page, page_size=page_size, status=status, user_id=_ANONYMOUS_USER_ID
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    summaries = []
    for p in result.projects:
        summaries.append(
            PresentationSummary(
                project_id=p.project_id,
                title=p.title,
                topic=p.topic,
                scenario=p.scenario,
                status=p.status,
                slides_count=len(p.slides_data) if p.slides_data else None,
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

@router.get("/{project_id}", response_model=PresentationDetail, summary="获取 PPT 详情")
async def get_presentation(project_id: str):
    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    project = await ppt_service.project_manager.get_project(project_id, user_id=_ANONYMOUS_USER_ID)
    if project is None:
        raise HTTPException(status_code=404, detail="PPT 不存在")

    return PresentationDetail(
        project_id=project.project_id,
        title=project.title,
        topic=project.topic,
        scenario=project.scenario,
        status=project.status,
        requirements=project.requirements,
        outline=project.outline,
        has_slides=bool(project.slides_html),
        slides_count=len(project.slides_data) if project.slides_data else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# ---------------------------------------------------------------------------
# DELETE /v1/presentations/{project_id}
# ---------------------------------------------------------------------------

@router.delete("/{project_id}", summary="删除 PPT")
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
# GET /v1/presentations/{project_id}/download  (HTML only — immediate)
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}/download",
    summary="下载 PPT — HTML 格式（立即返回）",
    description=(
        "返回生成完成的 PPT HTML 内容。仅支持 `format=html`（默认）。\n\n"
        "**PDF / PPTX 导出**请使用 `POST /v1/presentations/{project_id}/exports?format=pdf|pptx`，"
        " 该接口提交一个异步导出任务，完成后通过 `GET /v1/jobs/{job_id}/download` 下载文件。"
    ),
)
async def download_presentation(
    project_id: str,
    format: str = Query("html", description="当前仅支持 html；PDF/PPTX 请用 POST /exports"),
):
    if format != "html":
        raise HTTPException(
            status_code=400,
            detail=(
                f"format='{format}' 不支持直接下载。"
                " PDF/PPTX 请先 POST /v1/presentations/{project_id}/exports?format=pdf|pptx 提交导出任务，"
                " 完成后从 GET /v1/jobs/{job_id}/download 下载。"
            ),
        )

    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    project = await ppt_service.project_manager.get_project(project_id, user_id=_ANONYMOUS_USER_ID)
    if project is None:
        raise HTTPException(status_code=404, detail="PPT 不存在")
    if not project.slides_html:
        raise HTTPException(status_code=400, detail="PPT 尚未生成完成，请先确认任务 status=completed")

    return HTMLResponse(content=project.slides_html)


# ---------------------------------------------------------------------------
# POST /v1/presentations/{project_id}/exports  (PDF / PPTX — async job)
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/exports",
    status_code=202,
    summary="提交 PDF / PPTX 导出任务",
    description=(
        "提交一个导出任务。立即返回 `job_id`。\n\n"
        "- 通过 `GET /v1/jobs/{job_id}` 轮询状态\n"
        "- `status=completed` 后通过 `GET /v1/jobs/{job_id}/download` 下载文件\n\n"
        "**PDF** 依赖 Playwright（Chromium）渲染。"
        " **PPTX** 额外依赖 Apryse SDK（需 `ENABLE_APRYSE_PPTX_EXPORT=true` 和有效 `APRYSE_LICENSE_KEY`）。"
    ),
)
async def create_export(
    project_id: str,
    format: str = Query("pdf", description="导出格式: pdf / pptx"),
):
    if format not in ("pdf", "pptx"):
        raise HTTPException(status_code=400, detail="format 仅支持 pdf 或 pptx")

    ppt_service = get_ppt_service_for_user(_ANONYMOUS_USER_ID)
    project = await ppt_service.project_manager.get_project(project_id, user_id=_ANONYMOUS_USER_ID)
    if project is None:
        raise HTTPException(status_code=404, detail="PPT 不存在")
    if not project.slides_data:
        raise HTTPException(status_code=400, detail="PPT 尚未生成完成，无法导出")

    task_fn = _run_pdf_export if format == "pdf" else _run_pptx_export
    task_type = "pdf_export" if format == "pdf" else "pptx_export"

    task_manager = get_task_manager()
    job_id = task_manager.submit_task(
        task_type,
        task_fn,
        project_id,
        _ANONYMOUS_USER_ID,
        metadata={"project_id": project_id, "format": format},
    )
    logger.info("Export job submitted job_id=%s project_id=%s format=%s", job_id, project_id, format)

    return {
        "job_id": job_id,
        "project_id": project_id,
        "format": format,
        "status": "pending",
        "message": f"导出任务已提交。GET /v1/jobs/{job_id} 轮询，完成后 GET /v1/jobs/{job_id}/download 下载。",
    }
