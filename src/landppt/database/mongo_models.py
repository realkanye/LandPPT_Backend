"""
MongoDB document models using Beanie ODM.

Collection layout:
  projects               - ProjectDocument  (embeds todo_board + ppt_templates)
  slides                 - SlideDocument    (one doc per slide)
  project_versions       - ProjectVersionDocument
  global_master_templates- GlobalMasterTemplateDocument
  counters               - CounterDocument  (auto-increment integer IDs)
"""

import time
from typing import Any, Dict, List, Optional

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel


# ---------------------------------------------------------------------------
# Embedded models (stored inside ProjectDocument)
# ---------------------------------------------------------------------------

class TodoStageEmbed(BaseModel):
    stage_id: str
    stage_index: int
    title: str
    description: str
    status: str = "pending"
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class TodoBoardEmbed(BaseModel):
    current_stage_index: int = 0
    overall_progress: float = 0.0
    stages: List[TodoStageEmbed] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class PPTTemplateEmbed(BaseModel):
    id: int  # local sequential ID within the project
    template_type: str
    template_name: str
    description: Optional[str] = None
    html_template: str
    applicable_scenarios: Optional[List[str]] = None
    style_config: Optional[Dict[str, Any]] = None
    usage_count: int = 0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # project_id field so that code that does template.project_id still works
    project_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level documents (one collection per class)
# ---------------------------------------------------------------------------

class ProjectDocument(Document):
    project_id: str
    user_id: int
    title: str
    scenario: str
    topic: str
    requirements: Optional[str] = None
    status: str = "draft"
    outline: Optional[Dict[str, Any]] = None
    slides_html: Optional[str] = None
    confirmed_requirements: Optional[Dict[str, Any]] = None
    project_metadata: Optional[Dict[str, Any]] = None
    version: int = 1
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # Embedded sub-documents
    todo_board: Optional[TodoBoardEmbed] = None
    ppt_templates: List[PPTTemplateEmbed] = Field(default_factory=list)
    ppt_template_counter: int = 0  # auto-increment for PPTTemplateEmbed.id

    class Settings:
        name = "projects"
        indexes = [
            IndexModel([("project_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("updated_at", DESCENDING)]),
            IndexModel([("status", ASCENDING)]),
        ]


class SlideDocument(Document):
    project_id: str
    slide_index: int
    slide_id: str
    title: str
    content_type: str
    html_content: str
    slide_metadata: Optional[Dict[str, Any]] = None
    template_type: Optional[str] = None
    is_user_edited: bool = False
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    class Settings:
        name = "slides"
        indexes = [
            IndexModel(
                [("project_id", ASCENDING), ("slide_index", ASCENDING)],
                unique=True,
            ),
            IndexModel([("project_id", ASCENDING)]),
        ]


class ProjectVersionDocument(Document):
    project_id: str
    version: int
    timestamp: float = Field(default_factory=time.time)
    data: Dict[str, Any]
    description: str

    class Settings:
        name = "project_versions"
        indexes = [
            IndexModel([("project_id", ASCENDING)]),
            IndexModel([("project_id", ASCENDING), ("version", DESCENDING)]),
        ]


class GlobalMasterTemplateDocument(Document):
    """
    Integer primary key stored as MongoDB _id so existing API contracts
    (template.id == int) continue to work without any proxy layer.
    """

    id: Optional[int] = None  # set to next counter value before insert
    user_id: Optional[int] = None
    template_name: str
    description: Optional[str] = None
    html_template: str
    preview_image: Optional[str] = None
    style_config: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)
    is_default: bool = False
    is_active: bool = True
    usage_count: int = 0
    created_by: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    class Settings:
        name = "global_master_templates"
        indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel(
                [("is_active", ASCENDING), ("is_default", DESCENDING), ("usage_count", DESCENDING)]
            ),
            IndexModel([("template_name", ASCENDING)]),
        ]


class CounterDocument(Document):
    """Simple auto-increment counter collection."""

    name: str
    value: int = 0

    class Settings:
        name = "counters"
        indexes = [
            IndexModel([("name", ASCENDING)], unique=True),
        ]


class UserConfigDocument(Document):
    """Per-user (or system-level) configuration key-value store."""

    user_id: Optional[int] = None  # None = system-level default
    config_key: str
    config_value: Optional[str] = None
    config_type: str = "text"
    category: str = "general"

    class Settings:
        name = "user_configs"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("config_key", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
        ]
