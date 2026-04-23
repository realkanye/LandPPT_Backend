"""
Job status and file download endpoints for async tasks.
"""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .models import JobStatusResponse
from ...services.background_tasks import TaskStatus, get_task_manager

router = APIRouter()


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="查询任务状态",
    description=(
        "轮询异步任务的执行状态。\n\n"
        "`status` 取值: `pending` / `running` / `completed` / `failed` / `cancelled`\n\n"
        "- **PPT 生成任务**完成后，使用 `project_id` 调用 `GET /v1/presentations/{project_id}/download?format=html`\n"
        "- **导出任务**（PDF/PPTX）完成后，使用 `GET /v1/jobs/{job_id}/download` 下载文件"
    ),
)
async def get_job_status(job_id: str):
    task_manager = get_task_manager()
    task = await task_manager.get_task_async(job_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {job_id}")

    return JobStatusResponse(
        job_id=task.task_id,
        status=task.status.value,
        progress=task.progress,
        project_id=task.metadata.get("project_id"),
        error=task.error,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


@router.get(
    "/{job_id}/download",
    summary="下载导出文件",
    description=(
        "下载已完成的导出任务产生的文件（PDF 或 PPTX）。\n\n"
        "仅在 `status=completed` 后有效。文件下载后临时文件会被自动清理。"
    ),
)
async def download_job_file(job_id: str):
    task_manager = get_task_manager()
    task = await task_manager.get_task_async(job_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {job_id}")

    if task.status == TaskStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"任务执行失败，无法下载。错误: {task.error or '未知错误'}",
        )
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"任务尚未完成（当前状态: {task.status.value}），请稍后再试",
        )

    result = task.result
    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="任务结果格式异常，无法下载")

    file_path: str = result.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="导出文件不存在或已被清理，请重新提交导出任务")

    filename = result.get("filename") or os.path.basename(file_path)
    media_type = result.get("media_type", "application/octet-stream")

    def _cleanup():
        try:
            os.unlink(file_path)
        except OSError:
            pass

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
        background=BackgroundTask(_cleanup),
    )
