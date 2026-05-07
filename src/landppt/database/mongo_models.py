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
    # SVG documents (one per slide, in display order). Source-of-truth for
    # the editable-PPTX export pipeline ported from ppt-master.
    slides_svg: Optional[List[str]] = None
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


class UserDocument(Document):
    """User document model."""

    id: Optional[int] = None  # Integer primary key
    username: str
    password_hash: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    credits_balance: int = 0
    created_at: float = Field(default_factory=time.time)
    last_login: Optional[float] = None
    register_ip: Optional[str] = None
    last_login_ip: Optional[str] = None
    registration_channel: Optional[str] = None
    invite_code_id: Optional[int] = None
    github_id: Optional[str] = None
    linuxdo_id: Optional[str] = None
    oauth_provider: Optional[str] = None

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("email", ASCENDING)], unique=True, partialFilterExpression={"email": {"$exists": True}}),
            IndexModel([("github_id", ASCENDING)], unique=True, partialFilterExpression={"github_id": {"$exists": True}}),
            IndexModel([("linuxdo_id", ASCENDING)], unique=True, partialFilterExpression={"linuxdo_id": {"$exists": True}}),
        ]


class UserSessionDocument(Document):
    """User session document model."""

    session_id: str
    user_id: int
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: float
    created_at: float = Field(default_factory=time.time)
    last_used_at: Optional[float] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_revoked: bool = False

    class Settings:
        name = "user_sessions"
        indexes = [
            IndexModel([("session_id", ASCENDING)], unique=True),
            IndexModel([("access_token", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)]),
        ]


class UserAPIKeyDocument(Document):
    """User API key document model."""

    id: Optional[int] = None
    user_id: int
    key_name: str
    key_hash: str
    prefix: str
    permissions: List[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: float = Field(default_factory=time.time)
    last_used_at: Optional[float] = None
    expires_at: Optional[float] = None
    usage_count: int = 0

    class Settings:
        name = "user_api_keys"
        indexes = [
            IndexModel([("key_hash", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("user_id", ASCENDING), ("key_name", ASCENDING)], unique=True),
        ]


class CreditTransactionDocument(Document):
    """Credit transaction document model."""

    id: Optional[int] = None
    user_id: int
    amount: int
    balance_after: int
    transaction_type: str
    description: Optional[str] = None
    reference_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)

    class Settings:
        name = "credit_transactions"
        indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("transaction_type", ASCENDING)]),
        ]


class RedemptionCodeDocument(Document):
    """Redemption code document model."""

    id: Optional[int] = None
    code: str
    credits: int
    is_used: bool = False
    used_by: Optional[int] = None
    used_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None

    class Settings:
        name = "redemption_codes"
        indexes = [
            IndexModel([("code", ASCENDING)], unique=True),
            IndexModel([("is_used", ASCENDING)]),
        ]


# ---------------------------------------------------------------------------
# NarrationAudioDocument
# ---------------------------------------------------------------------------

class NarrationAudioDocument(Document):
    """Narration audio cache document."""

    id: Optional[int] = None
    project_id: str
    slide_index: int
    language: str = "zh"
    provider: str
    voice: str
    rate: str
    audio_format: str
    content_hash: str
    file_path: str
    duration_ms: Optional[int] = None
    cues_json: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    class Settings:
        name = "narration_audio"
        indexes = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("slide_index", ASCENDING),
                    ("language", ASCENDING),
                    ("provider", ASCENDING),
                    ("voice", ASCENDING),
                    ("rate", ASCENDING),
                    ("content_hash", ASCENDING),
                ],
                unique=True,
            ),
        ]


# ---------------------------------------------------------------------------
# DailyCheckInDocument
# ---------------------------------------------------------------------------

class DailyCheckInDocument(Document):
    """Daily check-in record."""

    id: Optional[int] = None
    user_id: int
    checkin_date: str  # YYYY-MM-DD format
    reward_points: int = 0
    created_at: float = Field(default_factory=time.time)

    class Settings:
        name = "daily_checkins"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("checkin_date", ASCENDING)], unique=True),
            IndexModel([("checkin_date", ASCENDING)]),
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "checkin_date": self.checkin_date,
            "reward_points": self.reward_points,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# InviteCodeDocument
# ---------------------------------------------------------------------------

class InviteCodeDocument(Document):
    """Registration invite code."""

    id: Optional[int] = None
    code: str
    channel: str
    credits_amount: int = 0
    max_uses: int = 1
    used_count: int = 0
    is_active: bool = True
    expires_at: Optional[float] = None
    created_by: Optional[int] = None
    description: Optional[str] = None
    created_at: float = Field(default_factory=time.time)

    class Settings:
        name = "invite_codes"
        indexes = [
            IndexModel([("code", ASCENDING)], unique=True),
            IndexModel([("channel", ASCENDING)]),
            IndexModel([("is_active", ASCENDING)]),
            IndexModel([("created_by", ASCENDING)]),
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "channel": self.channel,
            "credits_amount": self.credits_amount,
            "max_uses": self.max_uses,
            "used_count": self.used_count,
            "is_active": self.is_active,
            "expires_at": self.expires_at,
            "created_by": self.created_by,
            "description": self.description,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# InviteCodeUsageDocument
# ---------------------------------------------------------------------------

class InviteCodeUsageDocument(Document):
    """Invite code usage record."""

    id: Optional[int] = None
    invite_code_id: int
    user_id: int
    channel: str
    credits_granted: int = 0
    created_at: float = Field(default_factory=time.time)

    class Settings:
        name = "invite_code_usages"
        indexes = [
            IndexModel([("invite_code_id", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)], unique=True),
            IndexModel([("channel", ASCENDING)]),
        ]


# ---------------------------------------------------------------------------
# SponsorProfileDocument
# ---------------------------------------------------------------------------

class SponsorProfileDocument(Document):
    """Sponsor profile for sponsor page."""

    id: Optional[int] = None
    nickname: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    link_url: Optional[str] = None
    amount: Optional[str] = None
    note: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    class Settings:
        name = "sponsor_profiles"
        indexes = [
            IndexModel([("is_active", ASCENDING)]),
            IndexModel([("sort_order", ASCENDING)]),
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nickname": self.nickname,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "link_url": self.link_url,
            "amount": self.amount,
            "note": self.note,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
