"""
Compatibility shim — re-exports Beanie document models under the old
SQLAlchemy model names so that any remaining import of
`from .models import Project, SlideData, ...` continues to work.
"""

from .mongo_models import (
    ProjectDocument as Project,
    SlideDocument as SlideData,
    ProjectVersionDocument as ProjectVersion,
    GlobalMasterTemplateDocument as GlobalMasterTemplate,
    PPTTemplateEmbed as PPTTemplate,
    TodoBoardEmbed as TodoBoard,
    TodoStageEmbed as TodoStage,
    CounterDocument,
    UserConfigDocument as UserConfig,
)

# SQLAlchemy declarative_base stub — kept so any surviving code that does
# `from .models import Base` does not break at import time.
class _FakeBase:
    metadata = type("_FakeMeta", (), {"create_all": lambda *a, **kw: None, "sorted_tables": []})()

Base = _FakeBase()

__all__ = [
    "Project",
    "SlideData",
    "ProjectVersion",
    "GlobalMasterTemplate",
    "PPTTemplate",
    "TodoBoard",
    "TodoStage",
    "UserConfig",
    "Base",
]
