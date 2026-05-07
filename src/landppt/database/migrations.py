"""
Database migrations — MongoDB edition.

SQL migrations are no longer needed. This module keeps its public interface
(migration_manager) so imports elsewhere compile without changes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class _NoOpMigrationManager:
    """Stub migration manager — MongoDB needs no SQL migrations."""

    async def get_migration_status(self) -> dict:
        return {"pending_migrations": [], "applied_migrations": [], "total": 0}

    async def migrate_up(self) -> bool:
        logger.info("Migrations: MongoDB deployment — no SQL migrations to run")
        return True

    async def migrate_down(self, steps: int = 1) -> bool:
        return True


migration_manager = _NoOpMigrationManager()
