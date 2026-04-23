"""
MongoDB connection management — replaces the old SQLAlchemy database.py.

Compatibility contract kept for all existing callers:
  - `AsyncSessionLocal()` still works as both a direct call and async context manager.
    It returns a no-op _NoOpSession whose .close() is a no-op.
  - `init_db()` initialises Motor + Beanie.
  - `close_db()` disposes the Motor client.
  - `get_async_db()` / `get_db()` kept as stubs so FastAPI dependencies compile.
"""

from __future__ import annotations

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from ..core.config import app_config
from .mongo_models import (
    ProjectDocument,
    SlideDocument,
    ProjectVersionDocument,
    GlobalMasterTemplateDocument,
    CounterDocument,
    UserConfigDocument,
)

logger = logging.getLogger(__name__)

_mongo_client: Optional[AsyncIOMotorClient] = None


# ---------------------------------------------------------------------------
# No-op session shim
# ---------------------------------------------------------------------------

class _NoOpSession:
    """Replaces SQLAlchemy AsyncSession; all DB work goes through Beanie."""

    async def close(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def __aenter__(self) -> "_NoOpSession":
        return self

    async def __aexit__(self, *args) -> None:
        pass


class _NoOpSessionFactory:
    """
    Drop-in replacement for `async_sessionmaker(...)`.

    Callers do either:
      session = AsyncSessionLocal()            # direct call
      async with AsyncSessionLocal() as s: … # context manager
    Both patterns are supported.
    """

    def __call__(self) -> _NoOpSession:
        return _NoOpSession()

    # Support `async with AsyncSessionLocal() as s:` where the factory
    # itself is used as the context manager (rare, but happens).
    async def __aenter__(self) -> _NoOpSession:
        return _NoOpSession()

    async def __aexit__(self, *args) -> None:
        pass


AsyncSessionLocal: _NoOpSessionFactory = _NoOpSessionFactory()


# ---------------------------------------------------------------------------
# MongoDB initialisation
# ---------------------------------------------------------------------------

def _parse_db_name(url: str) -> str:
    """Extract the database name from a MongoDB connection URL."""
    path = (url or "").split("/")[-1].split("?")[0].strip()
    return path or "landppt"


async def init_db() -> None:
    """Initialise Motor client and Beanie ODM (called once at startup)."""
    global _mongo_client

    mongodb_url: str = getattr(
        app_config,
        "mongodb_url",
        "mongodb://localhost:27017/landppt",
    )
    db_name = _parse_db_name(mongodb_url)

    _mongo_client = AsyncIOMotorClient(mongodb_url)
    database = _mongo_client[db_name]

    await init_beanie(
        database=database,
        document_models=[
            ProjectDocument,
            SlideDocument,
            ProjectVersionDocument,
            GlobalMasterTemplateDocument,
            CounterDocument,
            UserConfigDocument,
        ],
    )
    logger.info("MongoDB initialised: db=%s url=%s", db_name, mongodb_url.split("@")[-1])


async def close_db() -> None:
    """Close the Motor client."""
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
        logger.info("MongoDB connection closed")


# ---------------------------------------------------------------------------
# Stubs kept for FastAPI dependency injection compatibility
# ---------------------------------------------------------------------------

async def get_async_db():
    """Stub generator — callers should use DatabaseService directly."""
    yield _NoOpSession()


def get_db():
    """Stub generator — callers should use DatabaseService directly."""
    yield None


# Sync session stub (legacy callers that haven't been converted to async).
# get_all_config_sync and similar methods now use asyncio.run() internally
# so they never actually call SessionLocal, but the import must resolve.
class _NoOpSyncSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, *args, **kwargs):
        return _NoOpSyncResult()


class _NoOpSyncResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None


class _NoOpSyncSessionFactory:
    def __call__(self) -> _NoOpSyncSession:
        return _NoOpSyncSession()

    def __enter__(self) -> _NoOpSyncSession:
        return _NoOpSyncSession()

    def __exit__(self, *args) -> None:
        pass


SessionLocal: _NoOpSyncSessionFactory = _NoOpSyncSessionFactory()
