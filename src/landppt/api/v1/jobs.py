"""
Job status endpoints for async PPT generation tasks.
"""

from fastapi import APIRouter, HTTPException

from .models import JobStatusResponse
from ...services.background_tasks import get_task_manager

router = APIRouter()


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="查询任务状态",
    description=(
        "轮询异步任务的执行状态。"
        " status 取值: pending / running / completed / failed / cancelled。"
        " 任务完成后使用 project_id 调用下载接口获取 PPT 文件。"
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
