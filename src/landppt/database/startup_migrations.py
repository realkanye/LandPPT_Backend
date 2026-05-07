"""
Startup migration runner — MongoDB edition.

SQL migrations are not needed for MongoDB. This module is kept so
startup_initialization.py can import it without changes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_startup_migrations() -> bool:
    """No-op for MongoDB deployments."""
    logger.info("Startup migrations: MongoDB deployment — skipping SQL migrations")
    return True
