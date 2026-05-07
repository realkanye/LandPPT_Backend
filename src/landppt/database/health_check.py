"""
Database health check utilities — MongoDB edition.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DatabaseHealthChecker:
    """MongoDB health check and diagnostics."""

    def __init__(self):
        self.checks = [
            {"name": "connection",    "description": "MongoDB connection test",        "check": self._check_connection,    "critical": True},
            {"name": "collections",   "description": "Collection existence",           "check": self._check_collections,   "critical": True},
            {"name": "data_integrity","description": "Basic data integrity",           "check": self._check_data_integrity,"critical": False},
            {"name": "performance",   "description": "MongoDB performance metrics",    "check": self._check_performance,   "critical": False},
        ]

    async def _check_connection(self) -> Dict[str, Any]:
        try:
            from .mongo_models import ProjectDocument
            col = ProjectDocument.get_motor_collection()
            await col.database.command("ping")
            return {"status": "healthy", "message": "MongoDB connection OK"}
        except Exception as exc:
            return {"status": "unhealthy", "message": str(exc)}

    async def _check_collections(self) -> Dict[str, Any]:
        try:
            from .mongo_models import (
                ProjectDocument, SlideDocument,
                ProjectVersionDocument, GlobalMasterTemplateDocument,
            )
            results = {}
            for doc_cls in [ProjectDocument, SlideDocument, ProjectVersionDocument, GlobalMasterTemplateDocument]:
                name = doc_cls.Settings.name
                count = await doc_cls.find().count()
                results[name] = count
            return {"status": "healthy", "collections": results}
        except Exception as exc:
            return {"status": "unhealthy", "message": str(exc)}

    async def _check_data_integrity(self) -> Dict[str, Any]:
        try:
            from .mongo_models import ProjectDocument, SlideDocument
            project_count = await ProjectDocument.find().count()
            slide_count = await SlideDocument.find().count()
            return {
                "status": "healthy",
                "projects": project_count,
                "slides": slide_count,
            }
        except Exception as exc:
            return {"status": "warning", "message": str(exc)}

    async def _check_performance(self) -> Dict[str, Any]:
        try:
            from .mongo_models import ProjectDocument
            start = time.time()
            await ProjectDocument.find().limit(1).to_list()
            elapsed_ms = (time.time() - start) * 1000
            return {
                "status": "healthy",
                "query_time_ms": round(elapsed_ms, 2),
            }
        except Exception as exc:
            return {"status": "warning", "message": str(exc)}

    async def run_all_checks(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        overall = "healthy"
        for check in self.checks:
            try:
                result = await check["check"]()
            except Exception as exc:
                result = {"status": "unhealthy", "message": str(exc)}
            results[check["name"]] = result
            if result.get("status") == "unhealthy" and check["critical"]:
                overall = "unhealthy"
            elif result.get("status") == "warning" and overall == "healthy":
                overall = "warning"
        return {"overall": overall, "checks": results}

    async def get_health_summary(self) -> Dict[str, Any]:
        return await self.run_all_checks()


health_checker = DatabaseHealthChecker()
