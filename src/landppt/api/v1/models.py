"""
Pydantic models for the v1 public API.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import time


class CreatePresentationRequest(BaseModel):
    topic: str = Field(..., description="PPT主题")
    scenario: str = Field(
        "general",
        description="场景类型: general / tourism / education / analysis / history / technology / business",
    )
    requirements: Optional[str] = Field(None, description="额外要求")
    language: str = Field("zh", description="语言: zh / en")
    target_audience: Optional[str] = Field(None, description="目标受众")
    ppt_style: str = Field("general", description="风格: general / conference / custom")
    custom_style_prompt: Optional[str] = Field(None, description="自定义风格描述（ppt_style=custom 时有效）")
    network_mode: bool = Field(False, description="是否启用联网搜索增强")
    uploaded_content: Optional[str] = Field(None, description="已上传文件的处理内容（来自 /v1/files/upload）")


class JobResponse(BaseModel):
    job_id: str = Field(..., description="任务ID，用于轮询状态")
    project_id: str = Field(..., description="项目ID，任务完成后用于下载")
    status: str = Field(..., description="初始状态，通常为 pending")
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str = Field(..., description="pending | running | completed | failed | cancelled")
    progress: float = Field(..., description="进度 0.0~100.0")
    project_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class PresentationSummary(BaseModel):
    project_id: str
    title: str
    topic: str
    scenario: str
    status: str
    slides_count: Optional[int] = None
    created_at: float
    updated_at: float


class PresentationDetail(PresentationSummary):
    requirements: Optional[str] = None
    outline: Optional[Dict[str, Any]] = None
    has_slides: bool = False


class PresentationListResponse(BaseModel):
    presentations: List[PresentationSummary]
    total: int
    page: int
    page_size: int


class FileUploadResponse(BaseModel):
    filename: str
    size: int
    file_type: str
    processed_content: str
    message: str
