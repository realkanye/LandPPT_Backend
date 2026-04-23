"""
Database service layer — MongoDB edition.

Drop-in replacement for the old SQLAlchemy-based service.py.
All public method signatures are identical so callers require no changes.
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple

from .mongo_models import (
    GlobalMasterTemplateDocument,
    PPTTemplateEmbed,
    ProjectDocument,
    SlideDocument,
)
from .repositories import (
    GlobalMasterTemplateRepository,
    PPTTemplateRepository,
    ProjectRepository,
    ProjectVersionRepository,
    SlideDataRepository,
    TodoBoardRepository,
    TodoStageRepository,
)
from ..api.models import (
    PPTGenerationRequest,
    PPTProject,
    ProjectListResponse,
    TodoBoard,
    TodoStage,
)

logger = logging.getLogger(__name__)

USER_SCOPE_ALL = -1


class _NullContextVar:
    def get(self):
        return None


current_user_id = _NullContextVar()


# ---------------------------------------------------------------------------
# DatabaseService
# ---------------------------------------------------------------------------

class DatabaseService:
    """
    MongoDB-backed service.  Constructor accepts a session argument for
    backward compatibility (the no-op _NoOpSession), but ignores it — all
    DB work goes through Beanie Document classes.
    """

    def __init__(self, session=None):
        self.session = session  # kept so callers can do `await db_service.session.close()`

        # Repo objects — exposed so callers that reach directly into repos
        # (e.g. db_project_manager.py) continue to work.
        self.project_repo = ProjectRepository()
        self.todo_board_repo = TodoBoardRepository()
        self.todo_stage_repo = TodoStageRepository()
        self.version_repo = ProjectVersionRepository()
        self.slide_repo = SlideDataRepository()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_progress(progress) -> float:
        try:
            value = float(progress)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(100.0, value))

    @classmethod
    def _calculate_overall_progress(cls, stages) -> float:
        if not stages:
            return 0.0
        return sum(cls._normalize_progress(getattr(s, "progress", 0.0)) for s in stages) / len(stages)

    @staticmethod
    def _extract_expected_slide_count(outline) -> int:
        if not isinstance(outline, dict):
            return 0
        slides = outline.get("slides")
        return len(slides) if isinstance(slides, list) else 0

    # ------------------------------------------------------------------
    # Project → API model conversion
    # ------------------------------------------------------------------

    def _convert_db_project_to_api(
        self,
        db_project: ProjectDocument,
        slides: Optional[List[SlideDocument]] = None,
    ) -> PPTProject:
        slides = slides or []

        # Build slides_data list from SlideDocument objects
        slides_data = []
        for slide in sorted(slides, key=lambda x: x.slide_index):
            slides_data.append({
                "slide_id": slide.slide_id,
                "title": slide.title,
                "content_type": slide.content_type,
                "html_content": slide.html_content,
                "metadata": slide.slide_metadata or {},
                "is_user_edited": slide.is_user_edited,
                "created_at": slide.created_at,
                "updated_at": slide.updated_at,
                "page_number": slide.slide_index + 1,
            })

        expected_slide_count = self._extract_expected_slide_count(db_project.outline)
        actual_slide_count = len(slides_data)
        has_confirmed_requirements = bool(db_project.confirmed_requirements)
        has_outline = expected_slide_count > 0
        has_any_ppt_output = actual_slide_count > 0 or bool(str(db_project.slides_html or "").strip())
        has_complete_ppt = actual_slide_count > 0 and (
            expected_slide_count == 0 or actual_slide_count >= expected_slide_count
        )

        todo_board = None
        if db_project.todo_board:
            raw_stages = db_project.todo_board.stages or []
            reconciled = []
            for stage in raw_stages:
                status = stage.status
                progress = self._normalize_progress(stage.progress)

                if stage.stage_id == "requirements_confirmation":
                    if has_confirmed_requirements:
                        status, progress = "completed", 100.0
                    elif status == "completed":
                        status, progress = "pending", 0.0
                elif stage.stage_id == "outline_generation":
                    if has_outline:
                        status, progress = "completed", 100.0
                    elif status == "completed":
                        status, progress = "pending", 0.0
                elif stage.stage_id == "ppt_creation":
                    if has_complete_ppt:
                        status, progress = "completed", 100.0
                    elif status == "completed":
                        if expected_slide_count > 0 and actual_slide_count > 0:
                            status = "running"
                            progress = min(99.0, (actual_slide_count / expected_slide_count) * 100)
                        elif has_any_ppt_output:
                            status = "running"
                            progress = max(progress, 1.0)
                        else:
                            status, progress = "pending", 0.0
                    elif (
                        expected_slide_count > 0
                        and actual_slide_count > 0
                        and status in {"pending", "running"}
                    ):
                        status = "running"
                        progress = max(
                            progress,
                            min(99.0, (actual_slide_count / expected_slide_count) * 100),
                        )

                if status == "completed":
                    progress = 100.0

                reconciled.append(
                    TodoStage(
                        id=stage.stage_id,
                        name=stage.title,
                        description=stage.description,
                        status=status,
                        progress=progress,
                        subtasks=[],
                        result=stage.result or {},
                        created_at=stage.created_at,
                        updated_at=stage.updated_at,
                    )
                )

            current_stage_index = len(reconciled) - 1 if reconciled else 0
            for i, s in enumerate(reconciled):
                if s.status != "completed":
                    current_stage_index = i
                    break

            todo_board = TodoBoard(
                task_id=db_project.project_id,
                title=db_project.title,
                stages=reconciled,
                current_stage_index=current_stage_index,
                overall_progress=self._calculate_overall_progress(reconciled),
                created_at=db_project.todo_board.created_at,
                updated_at=db_project.todo_board.updated_at,
            )

        project_status = db_project.status
        if project_status != "archived":
            if has_complete_ppt:
                project_status = "completed"
            elif has_confirmed_requirements or has_outline or has_any_ppt_output:
                project_status = "in_progress"
            else:
                project_status = "draft"

        return PPTProject(
            project_id=db_project.project_id,
            title=db_project.title,
            scenario=db_project.scenario,
            topic=db_project.topic,
            requirements=db_project.requirements,
            status=project_status,
            outline=db_project.outline,
            slides_html=db_project.slides_html,
            slides_data=slides_data,
            confirmed_requirements=db_project.confirmed_requirements,
            project_metadata=db_project.project_metadata,
            todo_board=todo_board,
            version=db_project.version,
            versions=[],
            created_at=db_project.created_at,
            updated_at=db_project.updated_at,
        )

    # ------------------------------------------------------------------
    # Project CRUD
    # ------------------------------------------------------------------

    async def create_project(
        self,
        request: PPTGenerationRequest,
        user_id: Optional[int] = None,
    ) -> PPTProject:
        project_id = str(uuid.uuid4())
        owner_id = user_id if user_id is not None else (current_user_id.get() or request.user_id)
        if owner_id is None:
            raise ValueError("user_id is required to create a project")

        project_data = {
            "project_id": project_id,
            "user_id": owner_id,
            "title": f"{request.topic} - {request.scenario}",
            "scenario": request.scenario,
            "topic": request.topic,
            "requirements": request.requirements,
            "status": "draft",
            "project_metadata": {
                "network_mode": request.network_mode,
                "language": request.language,
                "created_with_network_mode": request.network_mode,
            },
        }
        db_project = await self.project_repo.create(project_data)

        # Create embedded todo board with default stages
        from .mongo_models import TodoBoardEmbed, TodoStageEmbed
        now = time.time()
        stages = [
            TodoStageEmbed(
                stage_id="requirements_confirmation",
                stage_index=0,
                title="需求确认",
                description="确认PPT主题、内容重点、技术亮点和目标受众",
                status="pending",
                created_at=now,
                updated_at=now,
            ),
            TodoStageEmbed(
                stage_id="outline_generation",
                stage_index=1,
                title="大纲生成",
                description="基于确认的需求生成PPT大纲结构",
                status="pending",
                created_at=now,
                updated_at=now,
            ),
            TodoStageEmbed(
                stage_id="ppt_creation",
                stage_index=2,
                title="PPT生成",
                description="根据大纲生成完整的PPT页面",
                status="pending",
                created_at=now,
                updated_at=now,
            ),
        ]
        board = TodoBoardEmbed(
            current_stage_index=0,
            overall_progress=0.0,
            stages=stages,
            created_at=now,
            updated_at=now,
        )
        db_project.todo_board = board
        await db_project.save()

        return self._convert_db_project_to_api(db_project, [])

    async def get_project(
        self,
        project_id: str,
        user_id: Optional[int] = None,
    ) -> Optional[PPTProject]:
        db_project = await self.project_repo.get_by_id(project_id, user_id=user_id)
        if not db_project:
            return None
        slides = await self.slide_repo.get_slides_by_project_id(project_id)
        return self._convert_db_project_to_api(db_project, slides)

    async def list_projects(
        self,
        page: int = 1,
        page_size: int = 10,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ProjectListResponse:
        if status:
            total_candidates = await self.project_repo.count_projects(user_id=user_id)
            if total_candidates == 0:
                return ProjectListResponse(projects=[], total=0, page=page, page_size=page_size)

            db_projects = await self.project_repo.list_projects(
                user_id=user_id, page=1, page_size=total_candidates
            )
            all_api: List[PPTProject] = []
            for dp in db_projects:
                sl = await self.slide_repo.get_slides_by_project_id(dp.project_id)
                all_api.append(self._convert_db_project_to_api(dp, sl))

            filtered = [p for p in all_api if p.status == status]
            total = len(filtered)
            offset = max(page - 1, 0) * page_size
            projects = filtered[offset: offset + page_size]
        else:
            db_projects = await self.project_repo.list_projects(
                user_id=user_id, page=page, page_size=page_size
            )
            total = await self.project_repo.count_projects(user_id=user_id)
            projects = []
            for dp in db_projects:
                sl = await self.slide_repo.get_slides_by_project_id(dp.project_id)
                projects.append(self._convert_db_project_to_api(dp, sl))

        return ProjectListResponse(projects=projects, total=total, page=page, page_size=page_size)

    async def update_project_status(
        self,
        project_id: str,
        status: str,
        user_id: Optional[int] = None,
    ) -> bool:
        result = await self.project_repo.update(project_id, {"status": status}, user_id=user_id)
        return result is not None

    async def update_project(
        self,
        project_id: str,
        update_data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> bool:
        try:
            result = await self.project_repo.update(project_id, update_data, user_id=user_id)
            return result is not None
        except Exception as exc:
            logger.error("Failed to update project %s: %s", project_id, exc)
            return False

    # ------------------------------------------------------------------
    # Stage / board updates
    # ------------------------------------------------------------------

    async def update_stage_status(
        self,
        project_id: str,
        stage_id: str,
        status: str,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> bool:
        effective_user_id = user_id
        if effective_user_id == USER_SCOPE_ALL:
            effective_user_id = None
        if effective_user_id is None:
            effective_user_id = current_user_id.get()
        if effective_user_id is not None:
            project = await self.project_repo.get_by_id(project_id, user_id=effective_user_id)
            if not project:
                return False

        update_data: Dict[str, Any] = {"status": status}
        if progress is not None:
            update_data["progress"] = self._normalize_progress(progress)
        elif status == "completed":
            update_data["progress"] = 100.0
        if result is not None:
            update_data["result"] = result

        success = await self.todo_stage_repo.update_stage_by_project_and_stage(
            project_id, stage_id, update_data
        )

        if success:
            # Re-fetch project to get updated stages
            db_project = await ProjectDocument.find_one({"project_id": project_id})
            if db_project and db_project.todo_board:
                stages = db_project.todo_board.stages
                overall_progress = self._calculate_overall_progress(stages)
                current_stage_index = len(stages) - 1
                for i, s in enumerate(stages):
                    if s.status != "completed":
                        current_stage_index = i
                        break
                await self.todo_board_repo.update(project_id, {
                    "overall_progress": overall_progress,
                    "current_stage_index": current_stage_index,
                })
                logger.info(
                    "Updated TODO board: progress=%.1f%% current_stage=%d",
                    overall_progress, current_stage_index,
                )

        return success

    # ------------------------------------------------------------------
    # Outline
    # ------------------------------------------------------------------

    async def save_project_outline(
        self, project_id: str, outline: Dict[str, Any]
    ) -> bool:
        try:
            effective = current_user_id.get()
            if effective is not None:
                owned = await self.project_repo.get_by_id(project_id, user_id=effective)
                if not owned:
                    return False

            if not outline:
                logger.error("Outline data is empty")
                return False

            result = await self.project_repo.update(
                project_id, {"outline": outline, "updated_at": time.time()}
            )
            if result:
                logger.info("Saved outline for project %s", project_id)
                return True
            return False
        except Exception as exc:
            logger.error("Error saving outline for %s: %s", project_id, exc)
            return False

    # ------------------------------------------------------------------
    # Slides
    # ------------------------------------------------------------------

    def _build_slide_records(
        self,
        project_id: str,
        slides_data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        records = []
        for i, sd in enumerate(slides_data):
            records.append({
                "project_id": project_id,
                "slide_index": i,
                "slide_id": sd.get("slide_id", f"slide_{i}"),
                "title": sd.get("title", f"Slide {i + 1}"),
                "content_type": sd.get("content_type", "content"),
                "html_content": sd.get("html_content", ""),
                "slide_metadata": sd.get("metadata", {}),
                "is_user_edited": sd.get("is_user_edited", False),
            })
        return records

    async def save_project_slides(
        self,
        project_id: str,
        slides_html: str,
        slides_data: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        effective = current_user_id.get()
        if effective is not None:
            owned = await self.project_repo.get_by_id(project_id, user_id=effective)
            if not owned:
                return False

        # Persist slides to slides collection
        if slides_data:
            records = self._build_slide_records(project_id, slides_data)
            success = await self.slide_repo.batch_upsert_slides(project_id, records)
            if not success:
                return False

        # Update slides_html on the project document
        result = await self.project_repo.update(project_id, {"slides_html": slides_html})
        return result is not None

    async def replace_all_project_slides(
        self,
        project_id: str,
        slides_html: str,
        slides_data: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        effective = current_user_id.get()
        if effective is not None:
            owned = await self.project_repo.get_by_id(project_id, user_id=effective)
            if not owned:
                return False

        if slides_data:
            await self.slide_repo.delete_slides_by_project_id(project_id)
            records = self._build_slide_records(project_id, slides_data)
            await self.slide_repo.create_slides(records)

        result = await self.project_repo.update(project_id, {"slides_html": slides_html})
        return result is not None

    async def save_single_slide(
        self,
        project_id: str,
        slide_index: int,
        slide_data: Dict[str, Any],
        skip_if_user_edited: bool = False,
    ) -> bool:
        import asyncio

        effective = current_user_id.get()
        if effective is not None:
            owned = await self.project_repo.get_by_id(project_id, user_id=effective)
            if not owned:
                return False

        max_retries = 5
        base_delay = 0.1

        for attempt in range(max_retries):
            try:
                record = {
                    "project_id": project_id,
                    "slide_index": slide_index,
                    "slide_id": slide_data.get("slide_id", f"slide_{slide_index}"),
                    "title": slide_data.get("title", f"Slide {slide_index + 1}"),
                    "content_type": slide_data.get("content_type", "content"),
                    "html_content": slide_data.get("html_content", ""),
                    "slide_metadata": slide_data.get("metadata", {}),
                    "is_user_edited": slide_data.get("is_user_edited", False),
                }
                result = await self.slide_repo.upsert_slide(
                    project_id, slide_index, record,
                    skip_if_user_edited=skip_if_user_edited,
                )
                return result is not None
            except Exception as exc:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Slide save attempt %d failed, retrying in %.2fs: %s",
                        attempt + 1, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "save_single_slide failed after %d attempts: %s", max_retries, exc
                    )
                    return False
        return False

    async def cleanup_excess_slides(
        self,
        project_id: str,
        current_slide_count: int,
        user_id: Optional[int] = None,
    ) -> int:
        effective = user_id if user_id != USER_SCOPE_ALL else None
        if effective is None:
            effective = current_user_id.get()
        if effective is not None:
            owned = await self.project_repo.get_by_id(project_id, user_id=effective)
            if not owned:
                return 0
        deleted = await self.slide_repo.delete_slides_after_index(project_id, current_slide_count)
        logger.info("Cleaned up %d excess slides for %s", deleted, project_id)
        return deleted

    async def update_slide_user_edited_status(
        self,
        project_id: str,
        slide_index: int,
        is_user_edited: bool = True,
    ) -> bool:
        try:
            effective = current_user_id.get()
            if effective is not None:
                owned = await self.project_repo.get_by_id(project_id, user_id=effective)
                if not owned:
                    return False
            return await self.slide_repo.update_slide_user_edited_status(
                project_id, slide_index, is_user_edited
            )
        except Exception as exc:
            logger.error("Failed to update slide user_edited status: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Versions
    # ------------------------------------------------------------------

    async def save_project_version(
        self,
        project_id: str,
        version_data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> bool:
        project = await self.project_repo.get_by_id(project_id, user_id=user_id)
        if not project:
            return False

        version_info = {
            "project_id": project_id,
            "version": project.version,
            "timestamp": time.time(),
            "data": version_data,
            "description": f"Version {project.version} - {time.strftime('%Y-%m-%d %H:%M:%S')}",
        }
        await self.version_repo.create(version_info)
        await self.project_repo.update(
            project_id, {"version": project.version + 1}, user_id=user_id
        )
        return True

    # ------------------------------------------------------------------
    # PPT Templates (project-scoped, embedded)
    # ------------------------------------------------------------------

    async def create_template(
        self, template_data: Dict[str, Any]
    ) -> PPTTemplateEmbed:
        repo = PPTTemplateRepository()
        return await repo.create_template(template_data)

    async def get_template_by_id(self, template_id: int) -> Optional[PPTTemplateEmbed]:
        repo = PPTTemplateRepository()
        return await repo.get_template_by_id(template_id)

    async def get_templates_by_project_id(
        self, project_id: str
    ) -> List[PPTTemplateEmbed]:
        effective = current_user_id.get()
        if effective is not None:
            owned = await self.project_repo.get_by_id(project_id, user_id=effective)
            if not owned:
                return []
        repo = PPTTemplateRepository()
        return await repo.get_templates_by_project_id(project_id)

    async def get_templates_by_type(
        self, project_id: str, template_type: str
    ) -> List[PPTTemplateEmbed]:
        effective = current_user_id.get()
        if effective is not None:
            owned = await self.project_repo.get_by_id(project_id, user_id=effective)
            if not owned:
                return []
        repo = PPTTemplateRepository()
        return await repo.get_templates_by_type(project_id, template_type)

    async def update_template(self, template_id: int, update_data: Dict[str, Any]) -> bool:
        repo = PPTTemplateRepository()
        return await repo.update_template(template_id, update_data)

    async def increment_template_usage(self, template_id: int) -> bool:
        repo = PPTTemplateRepository()
        return await repo.increment_usage_count(template_id)

    async def delete_template(self, template_id: int) -> bool:
        repo = PPTTemplateRepository()
        return await repo.delete_template(template_id)

    async def delete_templates_by_project_id(self, project_id: str) -> bool:
        effective = current_user_id.get()
        if effective is not None:
            owned = await self.project_repo.get_by_id(project_id, user_id=effective)
            if not owned:
                return False
        repo = PPTTemplateRepository()
        return await repo.delete_templates_by_project_id(project_id)

    # ------------------------------------------------------------------
    # Global Master Templates
    # ------------------------------------------------------------------

    async def create_global_master_template(
        self,
        template_data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> GlobalMasterTemplateDocument:
        repo = GlobalMasterTemplateRepository()
        return await repo.create_template(template_data, user_id=user_id)

    async def get_global_master_template_by_id(
        self,
        template_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[GlobalMasterTemplateDocument]:
        repo = GlobalMasterTemplateRepository()
        return await repo.get_template_by_id(template_id, user_id=user_id)

    async def get_global_master_template_by_name(
        self,
        template_name: str,
        user_id: Optional[int] = None,
    ) -> Optional[GlobalMasterTemplateDocument]:
        repo = GlobalMasterTemplateRepository()
        return await repo.get_template_by_name(template_name, user_id=user_id)

    async def get_all_global_master_templates(
        self,
        active_only: bool = True,
        user_id: Optional[int] = None,
    ) -> List[GlobalMasterTemplateDocument]:
        repo = GlobalMasterTemplateRepository()
        return await repo.get_all_templates(active_only, user_id=user_id)

    async def get_global_master_templates_by_tags(
        self,
        tags: List[str],
        active_only: bool = True,
        user_id: Optional[int] = None,
    ) -> List[GlobalMasterTemplateDocument]:
        repo = GlobalMasterTemplateRepository()
        return await repo.get_templates_by_tags(tags, active_only, user_id=user_id)

    async def get_global_master_templates_paginated(
        self,
        active_only: bool = True,
        offset: int = 0,
        limit: int = 6,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[List[GlobalMasterTemplateDocument], int]:
        repo = GlobalMasterTemplateRepository()
        return await repo.get_templates_paginated(
            active_only, offset, limit, search, user_id=user_id
        )

    async def get_global_master_templates_by_tags_paginated(
        self,
        tags: List[str],
        active_only: bool = True,
        offset: int = 0,
        limit: int = 6,
        search: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[List[GlobalMasterTemplateDocument], int]:
        repo = GlobalMasterTemplateRepository()
        return await repo.get_templates_by_tags_paginated(
            tags, active_only, offset, limit, search, user_id=user_id
        )

    async def update_global_master_template(
        self,
        template_id: int,
        update_data: Dict[str, Any],
        user_id: Optional[int] = None,
        allow_system_write: bool = False,
    ) -> bool:
        repo = GlobalMasterTemplateRepository()
        return await repo.update_template(
            template_id, update_data, user_id=user_id,
            allow_system_write=allow_system_write,
        )

    async def delete_global_master_template(
        self,
        template_id: int,
        user_id: Optional[int] = None,
        allow_system_write: bool = False,
    ) -> bool:
        repo = GlobalMasterTemplateRepository()
        return await repo.delete_template(
            template_id, user_id=user_id,
            allow_system_write=allow_system_write,
        )

    async def increment_global_master_template_usage(
        self,
        template_id: int,
        user_id: Optional[int] = None,
    ) -> bool:
        repo = GlobalMasterTemplateRepository()
        return await repo.increment_usage_count(template_id, user_id=user_id)

    async def set_default_global_master_template(
        self,
        template_id: int,
        user_id: Optional[int] = None,
        allow_system_write: bool = False,
    ) -> bool:
        repo = GlobalMasterTemplateRepository()
        return await repo.set_default_template(
            template_id, user_id=user_id,
            allow_system_write=allow_system_write,
        )

    async def get_default_global_master_template(
        self,
        user_id: Optional[int] = None,
    ) -> Optional[GlobalMasterTemplateDocument]:
        repo = GlobalMasterTemplateRepository()
        return await repo.get_default_template(user_id=user_id)
