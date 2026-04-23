"""
File upload endpoint for the v1 API.
Accepts DOCX / PDF / TXT / MD, extracts text, and returns processed_content
that can be passed directly to CreatePresentationRequest.uploaded_content.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File

from .models import FileUploadResponse
from ...services.service_instances import get_ppt_service_for_user
from ...core.config import app_config

router = APIRouter()

_ALLOWED_EXTENSIONS = {".docx", ".pdf", ".txt", ".md"}


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    summary="上传源文档",
    description=(
        "上传 DOCX / PDF / TXT / MD 文件，服务器会提取并返回文本内容。"
        " 将返回的 processed_content 传给 POST /v1/presentations 的 uploaded_content 字段，"
        " 即可基于文档内容生成 PPT。"
    ),
)
async def upload_file(file: UploadFile = File(...)):
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 '{ext}'，支持: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    ppt_service = get_ppt_service_for_user(app_config.anonymous_user_id)

    try:
        processed = await ppt_service.process_uploaded_file(
            filename=file.filename,
            content=content,
            file_type=ext,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文件处理失败: {exc}") from exc

    return FileUploadResponse(
        filename=file.filename,
        size=len(content),
        file_type=ext,
        processed_content=processed,
        message="文件上传并处理成功，processed_content 可直接用于创建 PPT",
    )
