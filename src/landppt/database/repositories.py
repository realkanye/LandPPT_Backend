"""
MongoDB-backed repository classes — drop-in replacements for the old
SQLAlchemy repositories.  All public method signatures are identical so
that DatabaseService (service.py) and any direct repo callers work
without changes.
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from beanie.operators import In

from .mongo_models import (
    CounterDocument,
    GlobalMasterTemplateDocument,
    PPTTemplateEmbed,
    ProjectDocument,
    ProjectVersionDocument,
    SlideDocument,
    TodoBoardEmbed,
    TodoStageEmbed,
    UserConfigDocument,
    UserDocument,
    UserSessionDocument,
    UserAPIKeyDocument,
    CreditTransactionDocument,
    RedemptionCodeDocument,
    NarrationAudioDocument,
    DailyCheckInDocument,
    InviteCodeDocument,
    InviteCodeUsageDocument,
    SponsorProfileDocument,
)

logger = logging.getLogger(__name__)

USER_SCOPE_ALL = -1


def _effective_user_id(user_id: Optional[int]) -> Optional[int]:
    if user_id == USER_SCOPE_ALL:
        return None
    return user_id


# ---------------------------------------------------------------------------
# Counter helper
# ---------------------------------------------------------------------------

async def _next_counter(name: str) -> int:
    """Atomically increment a named counter and return the new value."""
    col = CounterDocument.get_pymongo_collection()
    doc = await col.find_one_and_update(
        {"name": name},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER,
    )
    return int(doc["value"])


# ---------------------------------------------------------------------------
# ProjectRepository
# ---------------------------------------------------------------------------

class ProjectRepository:

    async def create(self, project_data: Dict[str, Any]) -> ProjectDocument:
        doc = ProjectDocument(**project_data)
        await doc.insert()
        return doc

    async def get_by_id(
        self,
        project_id: str,
        user_id: Optional[int] = None,
    ) -> Optional[ProjectDocument]:
        effective = _effective_user_id(user_id)
        query: Dict[str, Any] = {"project_id": project_id}
        if effective is not None:
            query["user_id"] = effective
        return await ProjectDocument.find_one(query)

    async def list_projects(
        self,
        user_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 10,
        status: Optional[str] = None,
    ) -> List[ProjectDocument]:
        effective = _effective_user_id(user_id)
        query: Dict[str, Any] = {}
        if effective is not None:
            query["user_id"] = effective
        if status:
            query["status"] = status
        cursor = (
            ProjectDocument.find(query)
            .sort([("updated_at", pymongo.DESCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return await cursor.to_list()

    async def count_projects(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> int:
        effective = _effective_user_id(user_id)
        query: Dict[str, Any] = {}
        if effective is not None:
            query["user_id"] = effective
        if status:
            query["status"] = status
        return await ProjectDocument.find(query).count()

    async def update(
        self,
        project_id: str,
        update_data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Optional[ProjectDocument]:
        effective = _effective_user_id(user_id)
        query: Dict[str, Any] = {"project_id": project_id}
        if effective is not None:
            query["user_id"] = effective

        project = await ProjectDocument.find_one(query)
        if not project:
            logger.warning("No project found with ID %s for update", project_id)
            return None

        update_data["updated_at"] = time.time()
        for key, value in update_data.items():
            if hasattr(project, key):
                setattr(project, key, value)

        await project.save()
        return project

    async def delete(
        self,
        project_id: str,
        user_id: Optional[int] = None,
    ) -> bool:
        effective = _effective_user_id(user_id)
        query: Dict[str, Any] = {"project_id": project_id}
        if effective is not None:
            query["user_id"] = effective

        project = await ProjectDocument.find_one(query)
        if not project:
            return False

        # Cascade-delete related documents
        await SlideDocument.find({"project_id": project_id}).delete()
        await ProjectVersionDocument.find({"project_id": project_id}).delete()
        await project.delete()

        logger.info("Deleted project %s and all related documents", project_id)
        return True


# ---------------------------------------------------------------------------
# TodoBoardRepository
# ---------------------------------------------------------------------------

class TodoBoardRepository:
    """
    Todo boards are embedded in ProjectDocument.todo_board.
    This repository reads/writes that embedded sub-document.
    The returned objects are TodoBoardEmbed instances (not separate DB rows).
    """

    async def create(self, board_data: Dict[str, Any]) -> TodoBoardEmbed:
        project_id = board_data["project_id"]
        board = TodoBoardEmbed(
            current_stage_index=board_data.get("current_stage_index", 0),
            overall_progress=board_data.get("overall_progress", 0.0),
        )
        await ProjectDocument.find_one({"project_id": project_id}).update(
            {"$set": {"todo_board": board.model_dump()}}
        )
        return board

    async def get_by_project_id(self, project_id: str) -> Optional[TodoBoardEmbed]:
        project = await ProjectDocument.find_one({"project_id": project_id})
        return project.todo_board if project else None

    async def update(
        self,
        project_id: str,
        update_data: Dict[str, Any],
    ) -> Optional[TodoBoardEmbed]:
        update_data["updated_at"] = time.time()
        set_fields = {f"todo_board.{k}": v for k, v in update_data.items()}
        set_fields["updated_at"] = time.time()
        await ProjectDocument.find_one({"project_id": project_id}).update(
            {"$set": set_fields}
        )
        return await self.get_by_project_id(project_id)

    async def refresh(self, board: TodoBoardEmbed, project_id: str) -> TodoBoardEmbed:
        """Re-fetch the board from the database (replaces session.refresh)."""
        project = await ProjectDocument.find_one({"project_id": project_id})
        if project and project.todo_board:
            return project.todo_board
        return board


# ---------------------------------------------------------------------------
# TodoStageRepository
# ---------------------------------------------------------------------------

class TodoStageRepository:
    """Stages are embedded inside ProjectDocument.todo_board.stages."""

    async def create_stages(
        self,
        stages_data: List[Dict[str, Any]],
    ) -> List[TodoStageEmbed]:
        if not stages_data:
            return []

        project_id = stages_data[0]["project_id"]
        stages = [
            TodoStageEmbed(
                stage_id=sd["stage_id"],
                stage_index=sd["stage_index"],
                title=sd["title"],
                description=sd["description"],
                status=sd.get("status", "pending"),
            )
            for sd in stages_data
        ]
        stages_dicts = [s.model_dump() for s in stages]
        await ProjectDocument.find_one({"project_id": project_id}).update(
            {"$set": {"todo_board.stages": stages_dicts}}
        )
        return stages

    async def update_stage_by_project_and_stage(
        self,
        project_id: str,
        stage_id: str,
        update_data: Dict[str, Any],
    ) -> bool:
        update_data["updated_at"] = time.time()
        set_fields = {
            f"todo_board.stages.$[s].{k}": v
            for k, v in update_data.items()
        }
        col = ProjectDocument.get_pymongo_collection()
        result = await col.update_one(
            {"project_id": project_id},
            {"$set": set_fields},
            array_filters=[{"s.stage_id": stage_id}],
        )
        return result.modified_count > 0

    async def get_stage_by_project_and_stage(
        self,
        project_id: str,
        stage_id: str,
    ) -> Optional[TodoStageEmbed]:
        project = await ProjectDocument.find_one({"project_id": project_id})
        if not project or not project.todo_board:
            return None
        for stage in project.todo_board.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    async def update_stage(self, stage_id: str, update_data: Dict[str, Any]) -> bool:
        """Fallback: update by stage_id alone (requires a project scan)."""
        update_data["updated_at"] = time.time()
        col = ProjectDocument.get_pymongo_collection()
        set_fields = {f"todo_board.stages.$[s].{k}": v for k, v in update_data.items()}
        result = await col.update_one(
            {"todo_board.stages.stage_id": stage_id},
            {"$set": set_fields},
            array_filters=[{"s.stage_id": stage_id}],
        )
        return result.modified_count > 0

    async def get_stages_by_board_id(self, board_id: int) -> List[TodoStageEmbed]:
        """Not used in MongoDB path — boards have no separate integer id."""
        return []


# ---------------------------------------------------------------------------
# ProjectVersionRepository
# ---------------------------------------------------------------------------

class ProjectVersionRepository:

    async def create(self, version_data: Dict[str, Any]) -> ProjectVersionDocument:
        doc = ProjectVersionDocument(**version_data)
        await doc.insert()
        return doc

    async def get_versions_by_project_id(
        self, project_id: str
    ) -> List[ProjectVersionDocument]:
        return (
            await ProjectVersionDocument.find({"project_id": project_id})
            .sort([("version", pymongo.DESCENDING)])
            .to_list()
        )


# ---------------------------------------------------------------------------
# SlideDataRepository
# ---------------------------------------------------------------------------

class SlideDataRepository:

    async def create_slides(
        self, slides_data: List[Dict[str, Any]]
    ) -> List[SlideDocument]:
        docs = [SlideDocument(**sd) for sd in slides_data]
        if docs:
            await SlideDocument.insert_many(docs)
        return docs

    async def create_single_slide(self, slide_data: Dict[str, Any]) -> SlideDocument:
        doc = SlideDocument(**slide_data)
        await doc.insert()
        return doc

    async def upsert_slide(
        self,
        project_id: str,
        slide_index: int,
        slide_data: Dict[str, Any],
        skip_if_user_edited: bool = False,
    ) -> Optional[SlideDocument]:
        existing = await SlideDocument.find_one(
            {"project_id": project_id, "slide_index": slide_index}
        )
        if existing:
            if skip_if_user_edited and existing.is_user_edited:
                logger.info(
                    "Skipping user-edited slide project=%s index=%d",
                    project_id, slide_index,
                )
                return existing
            slide_data["updated_at"] = time.time()
            for key, value in slide_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await existing.save()
            return existing
        else:
            slide_data.setdefault("created_at", time.time())
            slide_data.setdefault("updated_at", time.time())
            doc = SlideDocument(**slide_data)
            await doc.insert()
            return doc

    async def get_slides_by_project_id(
        self, project_id: str
    ) -> List[SlideDocument]:
        return (
            await SlideDocument.find({"project_id": project_id})
            .sort([("slide_index", pymongo.ASCENDING)])
            .to_list()
        )

    async def get_slide_by_index(
        self, project_id: str, slide_index: int
    ) -> Optional[SlideDocument]:
        return await SlideDocument.find_one(
            {"project_id": project_id, "slide_index": slide_index}
        )

    async def update_slide(self, slide_id: str, update_data: Dict[str, Any]) -> bool:
        update_data["updated_at"] = time.time()
        slide = await SlideDocument.find_one({"slide_id": slide_id})
        if not slide:
            return False
        for k, v in update_data.items():
            if hasattr(slide, k):
                setattr(slide, k, v)
        await slide.save()
        return True

    async def delete_slides_by_project_id(self, project_id: str) -> bool:
        result = await SlideDocument.find({"project_id": project_id}).delete()
        return (result.deleted_count if result else 0) > 0

    async def delete_slides_after_index(
        self, project_id: str, start_index: int
    ) -> int:
        col = SlideDocument.get_pymongo_collection()
        result = await col.delete_many(
            {"project_id": project_id, "slide_index": {"$gte": start_index}}
        )
        deleted = result.deleted_count
        logger.debug("Deleted %d slides after index %d for %s", deleted, start_index, project_id)
        return deleted

    async def batch_upsert_slides(
        self, project_id: str, slides_data: List[Dict[str, Any]]
    ) -> bool:
        try:
            current_time = time.time()
            for i, sd in enumerate(slides_data):
                sd.setdefault("project_id", project_id)
                sd.setdefault("slide_index", i)
                await self.upsert_slide(project_id, i, sd)
            return True
        except Exception as exc:
            logger.error("batch_upsert_slides failed: %s", exc)
            return False

    async def update_slide_user_edited_status(
        self,
        project_id: str,
        slide_index: int,
        is_user_edited: bool = True,
    ) -> bool:
        slide = await SlideDocument.find_one(
            {"project_id": project_id, "slide_index": slide_index}
        )
        if not slide:
            return False
        slide.is_user_edited = is_user_edited
        slide.updated_at = time.time()
        await slide.save()
        return True


# ---------------------------------------------------------------------------
# PPTTemplateRepository  (templates are embedded in ProjectDocument)
# ---------------------------------------------------------------------------

class PPTTemplateRepository:

    async def create_template(
        self, template_data: Dict[str, Any]
    ) -> PPTTemplateEmbed:
        project_id = template_data["project_id"]
        template_data.setdefault("created_at", time.time())
        template_data.setdefault("updated_at", time.time())

        # Atomically increment the project-level template counter to get an int id
        col = ProjectDocument.get_pymongo_collection()
        updated = await col.find_one_and_update(
            {"project_id": project_id},
            {"$inc": {"ppt_template_counter": 1}},
            return_document=pymongo.ReturnDocument.AFTER,
        )
        template_data["id"] = updated["ppt_template_counter"]

        embed = PPTTemplateEmbed(**template_data)
        await ProjectDocument.find_one({"project_id": project_id}).update(
            {"$push": {"ppt_templates": embed.model_dump()}}
        )
        return embed

    async def get_template_by_id(
        self, template_id: int
    ) -> Optional[PPTTemplateEmbed]:
        project = await ProjectDocument.find_one(
            {"ppt_templates.id": template_id}
        )
        if not project:
            return None
        for t in project.ppt_templates:
            if t.id == template_id:
                return t
        return None

    async def get_templates_by_project_id(
        self, project_id: str
    ) -> List[PPTTemplateEmbed]:
        project = await ProjectDocument.find_one({"project_id": project_id})
        if not project:
            return []
        return sorted(project.ppt_templates, key=lambda t: t.created_at)

    async def get_templates_by_type(
        self, project_id: str, template_type: str
    ) -> List[PPTTemplateEmbed]:
        project = await ProjectDocument.find_one({"project_id": project_id})
        if not project:
            return []
        return [t for t in project.ppt_templates if t.template_type == template_type]

    async def update_template(
        self, template_id: int, update_data: Dict[str, Any]
    ) -> bool:
        update_data["updated_at"] = time.time()
        col = ProjectDocument.get_pymongo_collection()
        set_fields = {f"ppt_templates.$[t].{k}": v for k, v in update_data.items()}
        result = await col.update_one(
            {"ppt_templates.id": template_id},
            {"$set": set_fields},
            array_filters=[{"t.id": template_id}],
        )
        return result.modified_count > 0

    async def increment_usage_count(self, template_id: int) -> bool:
        col = ProjectDocument.get_pymongo_collection()
        result = await col.update_one(
            {"ppt_templates.id": template_id},
            {
                "$inc": {"ppt_templates.$[t].usage_count": 1},
                "$set": {"ppt_templates.$[t].updated_at": time.time()},
            },
            array_filters=[{"t.id": template_id}],
        )
        return result.modified_count > 0

    async def delete_template(self, template_id: int) -> bool:
        col = ProjectDocument.get_pymongo_collection()
        result = await col.update_one(
            {"ppt_templates.id": template_id},
            {"$pull": {"ppt_templates": {"id": template_id}}},
        )
        return result.modified_count > 0

    async def delete_templates_by_project_id(self, project_id: str) -> bool:
        result = await ProjectDocument.find_one({"project_id": project_id})
        if not result:
            return False
        await ProjectDocument.find_one({"project_id": project_id}).update(
            {"$set": {"ppt_templates": [], "ppt_template_counter": 0}}
        )
        return True


# ---------------------------------------------------------------------------
# GlobalMasterTemplateRepository
# ---------------------------------------------------------------------------

class GlobalMasterTemplateRepository:

    def _visibility_query(
        self,
        user_id: Optional[int],
        include_system: bool = True,
    ) -> Optional[Dict[str, Any]]:
        effective = _effective_user_id(user_id)
        if effective is None:
            return None  # no filter — see all templates
        if include_system:
            return {"$or": [{"user_id": effective}, {"user_id": None}]}
        return {"user_id": effective}

    def _merge(
        self,
        base: Dict[str, Any],
        extra: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if extra:
            if "$or" in extra and "$or" in base:
                # Combine with $and
                return {"$and": [base, extra]}
            base.update(extra)
        return base

    async def create_template(
        self,
        template_data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> GlobalMasterTemplateDocument:
        effective = _effective_user_id(user_id)
        if effective is not None and template_data.get("user_id") is None:
            template_data["user_id"] = effective

        template_data.setdefault("created_at", time.time())
        template_data.setdefault("updated_at", time.time())

        next_id = await _next_counter("global_master_templates")
        template_data["id"] = next_id

        doc = GlobalMasterTemplateDocument(**template_data)
        await doc.insert()
        return doc

    async def get_template_by_id(
        self,
        template_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[GlobalMasterTemplateDocument]:
        query: Dict[str, Any] = {"_id": template_id}
        vis = self._visibility_query(user_id)
        if vis:
            query = self._merge(query, vis)
        return await GlobalMasterTemplateDocument.find_one(query)

    async def get_template_by_name(
        self,
        template_name: str,
        user_id: Optional[int] = None,
    ) -> Optional[GlobalMasterTemplateDocument]:
        query: Dict[str, Any] = {"template_name": template_name}
        vis = self._visibility_query(user_id)
        if vis:
            query = self._merge(query, vis)
        return (
            await GlobalMasterTemplateDocument.find(query)
            .sort([("updated_at", pymongo.DESCENDING)])
            .limit(1)
            .first_or_none()
        )

    async def get_all_templates(
        self,
        active_only: bool = True,
        user_id: Optional[int] = None,
    ) -> List[GlobalMasterTemplateDocument]:
        query: Dict[str, Any] = {}
        vis = self._visibility_query(user_id)
        if vis:
            query = self._merge(query, vis)
        if active_only:
            query["is_active"] = True
        return (
            await GlobalMasterTemplateDocument.find(query)
            .sort([("is_default", pymongo.DESCENDING), ("usage_count", pymongo.DESCENDING)])
            .to_list()
        )

    async def get_templates_by_tags(
        self,
        tags: List[str],
        active_only: bool = True,
        user_id: Optional[int] = None,
    ) -> List[GlobalMasterTemplateDocument]:
        query: Dict[str, Any] = {"tags": {"$all": tags}}
        vis = self._visibility_query(user_id)
        if vis:
            query = self._merge(query, vis)
        if active_only:
            query["is_active"] = True
        return (
            await GlobalMasterTemplateDocument.find(query)
            .sort([("usage_count", pymongo.DESCENDING)])
            .to_list()
        )

    async def get_templates_paginated(
        self,
        active_only: bool = True,
        offset: int = 0,
        limit: int = 6,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[List[GlobalMasterTemplateDocument], int]:
        query: Dict[str, Any] = {}
        vis = self._visibility_query(user_id)
        if vis:
            query = self._merge(query, vis)
        if active_only:
            query["is_active"] = True
        if search and search.strip():
            pattern = {"$regex": search.strip(), "$options": "i"}
            query = self._merge(
                query,
                {"$or": [{"template_name": pattern}, {"description": pattern}]},
            )
        total = await GlobalMasterTemplateDocument.find(query).count()
        docs = (
            await GlobalMasterTemplateDocument.find(query)
            .sort([("is_default", pymongo.DESCENDING), ("usage_count", pymongo.DESCENDING)])
            .skip(offset)
            .limit(limit)
            .to_list()
        )
        return docs, total

    async def get_templates_by_tags_paginated(
        self,
        tags: List[str],
        active_only: bool = True,
        offset: int = 0,
        limit: int = 6,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[List[GlobalMasterTemplateDocument], int]:
        query: Dict[str, Any] = {"tags": {"$all": tags}}
        vis = self._visibility_query(user_id)
        if vis:
            query = self._merge(query, vis)
        if active_only:
            query["is_active"] = True
        if search and search.strip():
            pattern = {"$regex": search.strip(), "$options": "i"}
            query = self._merge(
                query,
                {"$or": [{"template_name": pattern}, {"description": pattern}]},
            )
        total = await GlobalMasterTemplateDocument.find(query).count()
        docs = (
            await GlobalMasterTemplateDocument.find(query)
            .sort([("usage_count", pymongo.DESCENDING)])
            .skip(offset)
            .limit(limit)
            .to_list()
        )
        return docs, total

    async def update_template(
        self,
        template_id: int,
        update_data: Dict[str, Any],
        user_id: Optional[int] = None,
        allow_system_write: bool = False,
    ) -> bool:
        effective = _effective_user_id(user_id)
        update_data["updated_at"] = time.time()

        query: Dict[str, Any] = {"_id": template_id}
        if effective is not None:
            if allow_system_write:
                query = self._merge(
                    query,
                    {"$or": [{"user_id": effective}, {"user_id": None}]},
                )
            else:
                query["user_id"] = effective

        col = GlobalMasterTemplateDocument.get_pymongo_collection()
        result = await col.update_one(query, {"$set": update_data})
        return result.modified_count > 0

    async def delete_template(
        self,
        template_id: int,
        user_id: Optional[int] = None,
        allow_system_write: bool = False,
    ) -> bool:
        effective = _effective_user_id(user_id)
        query: Dict[str, Any] = {"_id": template_id}
        if effective is not None:
            if allow_system_write:
                query = self._merge(
                    query,
                    {"$or": [{"user_id": effective}, {"user_id": None}]},
                )
            else:
                query["user_id"] = effective

        col = GlobalMasterTemplateDocument.get_pymongo_collection()
        result = await col.delete_one(query)
        rows = result.deleted_count
        logger.info("Delete template %d: %d rows affected", template_id, rows)
        return rows > 0

    async def increment_usage_count(
        self,
        template_id: int,
        user_id: Optional[int] = None,
    ) -> bool:
        effective = _effective_user_id(user_id)
        query: Dict[str, Any] = {"_id": template_id}
        if effective is not None:
            query = self._merge(
                query,
                {"$or": [{"user_id": effective}, {"user_id": None}]},
            )
        col = GlobalMasterTemplateDocument.get_pymongo_collection()
        result = await col.update_one(
            query,
            {
                "$inc": {"usage_count": 1},
                "$set": {"updated_at": time.time()},
            },
        )
        return result.modified_count > 0

    async def set_default_template(
        self,
        template_id: int,
        user_id: Optional[int] = None,
        allow_system_write: bool = False,
    ) -> bool:
        effective = _effective_user_id(user_id)
        col = GlobalMasterTemplateDocument.get_pymongo_collection()
        now = time.time()

        if effective is None:
            # Unscoped: clear all defaults, then set one
            await col.update_many({}, {"$set": {"is_default": False, "updated_at": now}})
            result = await col.update_one(
                {"_id": template_id},
                {"$set": {"is_default": True, "updated_at": now}},
            )
            return result.modified_count > 0

        # Scoped user: determine if target template is system or user-owned
        target = await col.find_one({"_id": template_id})
        if not target:
            return False

        target_user_id = target.get("user_id")

        if allow_system_write and target_user_id is None:
            # Clear system template defaults; set new one
            await col.update_many(
                {"user_id": None},
                {"$set": {"is_default": False, "updated_at": now}},
            )
            result = await col.update_one(
                {"_id": template_id, "user_id": None},
                {"$set": {"is_default": True, "updated_at": now}},
            )
            return result.modified_count > 0

        # Scoped: only affect this user's templates
        await col.update_many(
            {"user_id": effective},
            {"$set": {"is_default": False, "updated_at": now}},
        )
        result = await col.update_one(
            {"_id": template_id, "user_id": effective},
            {"$set": {"is_default": True, "updated_at": now}},
        )
        return result.modified_count > 0

    async def get_default_template(
        self,
        user_id: Optional[int] = None,
    ) -> Optional[GlobalMasterTemplateDocument]:
        effective = _effective_user_id(user_id)

        if effective is not None:
            # Try user's own default first
            user_default = await GlobalMasterTemplateDocument.find_one(
                {"user_id": effective, "is_default": True, "is_active": True}
            )
            if user_default:
                return user_default
            # Fall back to system default
            return await GlobalMasterTemplateDocument.find_one(
                {"user_id": None, "is_default": True, "is_active": True}
            )

        return await GlobalMasterTemplateDocument.find_one(
            {"is_default": True, "is_active": True}
        )


# ---------------------------------------------------------------------------
# UserConfigRepository
# ---------------------------------------------------------------------------

class UserConfigRepository:
    """MongoDB-backed per-user configuration store."""

    def __init__(self, session=None) -> None:
        pass  # session is a _NoOpSession; all operations go through Beanie

    async def get_all_configs(self, user_id: Optional[int]) -> Dict[str, Any]:
        docs = await UserConfigDocument.find(
            UserConfigDocument.user_id == user_id
        ).to_list()
        return {
            doc.config_key: {
                "value": doc.config_value,
                "type": doc.config_type,
                "category": doc.category,
            }
            for doc in docs
        }

    async def get_config(self, user_id: Optional[int], key: str) -> Optional[str]:
        doc = await UserConfigDocument.find_one(
            UserConfigDocument.user_id == user_id,
            UserConfigDocument.config_key == key,
        )
        return doc.config_value if doc else None

    async def set_config(
        self,
        user_id: Optional[int],
        key: str,
        value: Optional[str],
        config_type: str = "text",
        category: str = "general",
    ) -> None:
        existing = await UserConfigDocument.find_one(
            UserConfigDocument.user_id == user_id,
            UserConfigDocument.config_key == key,
        )
        if existing:
            existing.config_value = value
            existing.config_type = config_type
            existing.category = category
            await existing.save()
        else:
            await UserConfigDocument(
                user_id=user_id,
                config_key=key,
                config_value=value,
                config_type=config_type,
                category=category,
            ).insert()

    async def reset_user_configs(
        self, user_id: int, category: Optional[str] = None
    ) -> int:
        query = UserConfigDocument.find(UserConfigDocument.user_id == user_id)
        if category:
            query = query.find(UserConfigDocument.category == category)
        docs = await query.to_list()
        for doc in docs:
            await doc.delete()
        return len(docs)


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------

class UserRepository:
    """MongoDB-backed user repository."""

    def __init__(self, session=None) -> None:
        pass  # session is a _NoOpSession; all operations go through Beanie

    async def get_by_id(self, user_id: int) -> Optional[UserDocument]:
        """Get user by ID."""
        return await UserDocument.find_one(UserDocument.id == user_id)

    async def get_by_username(self, username: str) -> Optional[UserDocument]:
        """Get user by username."""
        return await UserDocument.find_one(UserDocument.username == username)

    async def get_by_email(self, email: str) -> Optional[UserDocument]:
        """Get user by email."""
        return await UserDocument.find_one(UserDocument.email == email)

    async def get_by_github_id(self, github_id: str) -> Optional[UserDocument]:
        """Get user by GitHub ID."""
        return await UserDocument.find_one(UserDocument.github_id == github_id)

    async def get_by_linuxdo_id(self, linuxdo_id: str) -> Optional[UserDocument]:
        """Get user by Linux.do ID."""
        return await UserDocument.find_one(UserDocument.linuxdo_id == linuxdo_id)

    async def create(self, user_data: Dict[str, Any]) -> UserDocument:
        """Create a new user."""
        # Assign ID if not provided
        if "id" not in user_data:
            user_data["id"] = await _next_counter("users")
        doc = UserDocument(**user_data)
        await doc.insert()
        return doc

    async def update_credits_balance(self, user_id: int, new_balance: int) -> None:
        """Update user's credits balance."""
        user = await self.get_by_id(user_id)
        if user:
            user.credits_balance = new_balance
            await user.save()

    async def update_last_login(self, user_id: int, ip_address: Optional[str] = None) -> None:
        """Update user's last login time and IP."""
        user = await self.get_by_id(user_id)
        if user:
            user.last_login = time.time()
            if ip_address:
                user.last_login_ip = ip_address
            await user.save()

    async def update_password_hash(self, user_id: int, password_hash: str) -> None:
        """Update user's password hash."""
        user = await self.get_by_id(user_id)
        if user:
            user.password_hash = password_hash
            await user.save()


# ---------------------------------------------------------------------------
# UserSessionRepository
# ---------------------------------------------------------------------------

class UserSessionRepository:
    """MongoDB-backed user session repository."""

    def __init__(self, session=None) -> None:
        pass

    async def create(self, session_data: Dict[str, Any]) -> UserSessionDocument:
        """Create a new session."""
        doc = UserSessionDocument(**session_data)
        await doc.insert()
        return doc

    async def get_by_session_id(self, session_id: str) -> Optional[UserSessionDocument]:
        """Get session by session ID."""
        return await UserSessionDocument.find_one(UserSessionDocument.session_id == session_id)

    async def get_by_access_token(self, access_token: str) -> Optional[UserSessionDocument]:
        """Get session by access token."""
        return await UserSessionDocument.find_one(UserSessionDocument.access_token == access_token)

    async def revoke_session(self, session_id: str) -> None:
        """Revoke a session."""
        session = await self.get_by_session_id(session_id)
        if session:
            session.is_revoked = True
            await session.save()

    async def delete_expired_sessions(self, cutoff_time: float) -> int:
        """Delete all expired sessions."""
        cursor = UserSessionDocument.find(UserSessionDocument.expires_at < cutoff_time)
        docs = await cursor.to_list()
        for doc in docs:
            await doc.delete()
        return len(docs)


# ---------------------------------------------------------------------------
# UserAPIKeyRepository
# ---------------------------------------------------------------------------

class UserAPIKeyRepository:
    """MongoDB-backed user API key repository."""

    def __init__(self, session=None) -> None:
        pass

    async def create(self, api_key_data: Dict[str, Any]) -> UserAPIKeyDocument:
        """Create a new API key."""
        if "id" not in api_key_data:
            api_key_data["id"] = await _next_counter("user_api_keys")
        doc = UserAPIKeyDocument(**api_key_data)
        await doc.insert()
        return doc

    async def get_by_key_hash(self, key_hash: str) -> Optional[UserAPIKeyDocument]:
        """Get API key by hash."""
        return await UserAPIKeyDocument.find_one(
            UserAPIKeyDocument.key_hash == key_hash,
            UserAPIKeyDocument.is_active == True,
        )

    async def list_by_user_id(self, user_id: int) -> List[UserAPIKeyDocument]:
        """List all API keys for a user."""
        return await UserAPIKeyDocument.find(
            UserAPIKeyDocument.user_id == user_id,
            UserAPIKeyDocument.is_active == True,
        ).to_list()

    async def revoke_key(self, key_id: int, user_id: Optional[int] = None) -> bool:
        """Revoke an API key."""
        query = {"id": key_id}
        if user_id is not None:
            query["user_id"] = user_id
        doc = await UserAPIKeyDocument.find_one(query)
        if doc:
            doc.is_active = False
            await doc.save()
            return True
        return False

    async def update_usage(self, key_id: int) -> None:
        """Increment usage count for an API key."""
        doc = await UserAPIKeyDocument.find_one(UserAPIKeyDocument.id == key_id)
        if doc:
            doc.usage_count += 1
            doc.last_used_at = time.time()
            await doc.save()


# ---------------------------------------------------------------------------
# CreditTransactionRepository
# ---------------------------------------------------------------------------

class CreditTransactionRepository:
    """MongoDB-backed credit transaction repository."""

    def __init__(self, session=None) -> None:
        pass

    async def create(self, transaction_data: Dict[str, Any]) -> CreditTransactionDocument:
        """Create a new transaction."""
        if "id" not in transaction_data:
            transaction_data["id"] = await _next_counter("credit_transactions")
        doc = CreditTransactionDocument(**transaction_data)
        await doc.insert()
        return doc

    async def get_by_user_id(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> List[CreditTransactionDocument]:
        """Get transactions for a user with pagination."""
        cursor = (
            CreditTransactionDocument.find(CreditTransactionDocument.user_id == user_id)
            .sort([("created_at", pymongo.DESCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return await cursor.to_list()

    async def count_by_user_id(self, user_id: int) -> int:
        """Count total transactions for a user."""
        return await CreditTransactionDocument.find(CreditTransactionDocument.user_id == user_id).count()


# ---------------------------------------------------------------------------
# RedemptionCodeRepository
# ---------------------------------------------------------------------------

class RedemptionCodeRepository:
    """MongoDB-backed redemption code repository."""

    def __init__(self, session=None) -> None:
        pass

    async def create(self, code_data: Dict[str, Any]) -> RedemptionCodeDocument:
        """Create a new redemption code."""
        if "id" not in code_data:
            code_data["id"] = await _next_counter("redemption_codes")
        doc = RedemptionCodeDocument(**code_data)
        await doc.insert()
        return doc

    async def get_by_code(self, code: str) -> Optional[RedemptionCodeDocument]:
        """Get redemption code by code string."""
        return await RedemptionCodeDocument.find_one(
            RedemptionCodeDocument.code == code,
            RedemptionCodeDocument.is_used == False,
        )

    async def mark_as_used(self, code_id: int, user_id: int) -> None:
        """Mark redemption code as used."""
        doc = await RedemptionCodeDocument.find_one(RedemptionCodeDocument.id == code_id)
        if doc:
            doc.is_used = True
            doc.used_by = user_id
            doc.used_at = time.time()
            await doc.save()


# ---------------------------------------------------------------------------
# NarrationAudioRepository
# ---------------------------------------------------------------------------

class NarrationAudioRepository:
    """MongoDB-backed narration audio repository."""

    def __init__(self, session=None) -> None:
        pass

    async def get_cached_audio(
        self,
        *,
        project_id: str,
        slide_index: int,
        language: str,
        provider: str,
        voice: str,
        rate: str,
        content_hash: str,
    ) -> Optional[NarrationAudioDocument]:
        """Get cached audio by unique key."""
        return await NarrationAudioDocument.find_one(
            NarrationAudioDocument.project_id == project_id,
            NarrationAudioDocument.slide_index == slide_index,
            NarrationAudioDocument.language == (language or "zh"),
            NarrationAudioDocument.provider == provider,
            NarrationAudioDocument.voice == voice,
            NarrationAudioDocument.rate == rate,
            NarrationAudioDocument.content_hash == content_hash,
        )

    async def upsert_audio(
        self,
        *,
        project_id: str,
        slide_index: int,
        language: str,
        provider: str,
        voice: str,
        rate: str,
        audio_format: str,
        content_hash: str,
        file_path: str,
        duration_ms: Optional[int],
        cues_json: Optional[str] = None,
    ) -> NarrationAudioDocument:
        """Upsert audio cache entry."""
        existing = await self.get_cached_audio(
            project_id=project_id,
            slide_index=slide_index,
            language=language,
            provider=provider,
            voice=voice,
            rate=rate,
            content_hash=content_hash,
        )

        if existing:
            existing.audio_format = audio_format
            existing.file_path = file_path
            existing.duration_ms = duration_ms
            if cues_json is not None:
                existing.cues_json = cues_json
            existing.updated_at = time.time()
            await existing.save()
            return existing

        doc = NarrationAudioDocument(
            project_id=project_id,
            slide_index=slide_index,
            language=(language or "zh"),
            provider=provider,
            voice=voice,
            rate=rate,
            audio_format=audio_format,
            content_hash=content_hash,
            file_path=file_path,
            duration_ms=duration_ms,
            cues_json=cues_json,
            created_at=time.time(),
            updated_at=time.time(),
        )
        await doc.insert()
        return doc

    async def get_by_project_id(self, project_id: str) -> List[NarrationAudioDocument]:
        """Get all audio entries for a project."""
        return await NarrationAudioDocument.find(
            NarrationAudioDocument.project_id == project_id
        ).to_list()

    async def delete_by_project_id(self, project_id: str) -> int:
        """Delete all audio entries for a project."""
        docs = await self.get_by_project_id(project_id)
        for doc in docs:
            await doc.delete()
        return len(docs)


# ---------------------------------------------------------------------------
# DailyCheckInRepository
# ---------------------------------------------------------------------------

class DailyCheckInRepository:
    """MongoDB-backed daily check-in repository."""

    def __init__(self, session=None) -> None:
        pass

    async def get_by_user_and_date(self, user_id: int, checkin_date: str) -> Optional[DailyCheckInDocument]:
        """Get check-in record by user ID and date."""
        return await DailyCheckInDocument.find_one(
            DailyCheckInDocument.user_id == user_id,
            DailyCheckInDocument.checkin_date == checkin_date,
        )

    async def create(self, checkin_data: Dict[str, Any]) -> DailyCheckInDocument:
        """Create a new check-in record."""
        doc = DailyCheckInDocument(**checkin_data)
        await doc.insert()
        return doc

    async def list_by_user_id(self, user_id: int, limit: int = 30) -> List[DailyCheckInDocument]:
        """List check-in records for a user."""
        return (
            await DailyCheckInDocument.find(DailyCheckInDocument.user_id == user_id)
            .sort([("created_at", pymongo.DESCENDING)])
            .limit(limit)
            .to_list()
        )


# ---------------------------------------------------------------------------
# InviteCodeRepository
# ---------------------------------------------------------------------------

class InviteCodeRepository:
    """MongoDB-backed invite code repository."""

    def __init__(self, session=None) -> None:
        pass

    async def get_by_id(self, invite_code_id: int) -> Optional[InviteCodeDocument]:
        """Get invite code by ID."""
        return await InviteCodeDocument.find_one(InviteCodeDocument.id == invite_code_id)

    async def get_by_code(self, code: str) -> Optional[InviteCodeDocument]:
        """Get invite code by code string (case-insensitive)."""
        col = InviteCodeDocument.get_pymongo_collection()
        result = await col.find_one({"code": {"$regex": f"^{code}$", "$options": "i"}})
        if result:
            return InviteCodeDocument.model_validate(result)
        return None

    async def create(self, invite_data: Dict[str, Any]) -> InviteCodeDocument:
        """Create a new invite code."""
        if "id" not in invite_data:
            invite_data["id"] = await _next_counter("invite_codes")
        doc = InviteCodeDocument(**invite_data)
        await doc.insert()
        return doc

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        channel: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[InviteCodeDocument], int]:
        """List invite codes with pagination and filters."""
        query: Dict[str, Any] = {}

        if search:
            pattern = {"$regex": search.strip(), "$options": "i"}
            query["$or"] = [{"code": pattern}, {"description": pattern}]

        if channel:
            query["channel"] = channel

        if is_active is not None:
            query["is_active"] = is_active

        total = await InviteCodeDocument.find(query).count()
        docs = (
            await InviteCodeDocument.find(query)
            .sort([("created_at", pymongo.DESCENDING), ("id", pymongo.DESCENDING)])
            .skip(max(page - 1, 0) * page_size)
            .limit(page_size)
            .to_list()
        )
        return docs, total

    async def update(self, invite_code_id: int, update_data: Dict[str, Any]) -> Optional[InviteCodeDocument]:
        """Update an invite code."""
        doc = await self.get_by_id(invite_code_id)
        if not doc:
            return None

        for key, value in update_data.items():
            if hasattr(doc, key):
                setattr(doc, key, value)

        await doc.save()
        return doc

    async def delete(self, invite_code_id: int) -> bool:
        """Delete an invite code (only if unused)."""
        doc = await self.get_by_id(invite_code_id)
        if not doc:
            return False
        if int(doc.used_count or 0) > 0:
            return False
        await doc.delete()
        return True


# ---------------------------------------------------------------------------
# InviteCodeUsageRepository
# ---------------------------------------------------------------------------

class InviteCodeUsageRepository:
    """MongoDB-backed invite code usage repository."""

    def __init__(self, session=None) -> None:
        pass

    async def get_by_id(self, usage_id: int) -> Optional[InviteCodeUsageDocument]:
        """Get usage record by ID."""
        return await InviteCodeUsageDocument.find_one(InviteCodeUsageDocument.id == usage_id)

    async def get_by_user_id(self, user_id: int) -> Optional[InviteCodeUsageDocument]:
        """Get usage record by user ID (a user can only use one invite code)."""
        return await InviteCodeUsageDocument.find_one(InviteCodeUsageDocument.user_id == user_id)

    async def get_by_invite_code_id(self, invite_code_id: int) -> List[InviteCodeUsageDocument]:
        """Get all usage records for an invite code."""
        return await InviteCodeUsageDocument.find(
            InviteCodeUsageDocument.invite_code_id == invite_code_id
        ).to_list()

    async def create(self, usage_data: Dict[str, Any]) -> InviteCodeUsageDocument:
        """Create a new usage record."""
        if "id" not in usage_data:
            usage_data["id"] = await _next_counter("invite_code_usages")
        doc = InviteCodeUsageDocument(**usage_data)
        await doc.insert()
        return doc


# ---------------------------------------------------------------------------
# SponsorProfileRepository
# ---------------------------------------------------------------------------

class SponsorProfileRepository:
    """MongoDB-backed sponsor profile repository."""

    def __init__(self, session=None) -> None:
        pass

    async def get_by_id(self, sponsor_id: int) -> Optional[SponsorProfileDocument]:
        """Get sponsor profile by ID."""
        return await SponsorProfileDocument.find_one(SponsorProfileDocument.id == sponsor_id)

    async def list_all(self, include_inactive: bool = True) -> List[SponsorProfileDocument]:
        """List all sponsor profiles."""
        query: Dict[str, Any] = {}
        if not include_inactive:
            query["is_active"] = True

        return (
            await SponsorProfileDocument.find(query)
            .sort([("sort_order", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
            .to_list()
        )

    async def create(self, sponsor_data: Dict[str, Any]) -> SponsorProfileDocument:
        """Create a new sponsor profile."""
        if "id" not in sponsor_data:
            sponsor_data["id"] = await _next_counter("sponsor_profiles")
        doc = SponsorProfileDocument(**sponsor_data)
        await doc.insert()
        return doc

    async def update(self, sponsor_id: int, update_data: Dict[str, Any]) -> Optional[SponsorProfileDocument]:
        """Update a sponsor profile."""
        doc = await self.get_by_id(sponsor_id)
        if not doc:
            return None

        for key, value in update_data.items():
            if hasattr(doc, key):
                setattr(doc, key, value)

        await doc.save()
        return doc

    async def delete(self, sponsor_id: int) -> bool:
        """Delete a sponsor profile."""
        doc = await self.get_by_id(sponsor_id)
        if not doc:
            return False
        await doc.delete()
        return True
