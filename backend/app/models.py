"""Models module - Re-exports for backward compatibility.

This module re-exports models from core.db.sqlmodel_models for
backward compatibility with existing code that imports from app.models.

⚠️ Item / ItemCreate 已随 D1.4 删除（模板残留的示例待办表）。
"""

from app.core.db.sqlmodel_models import (
    User,
    UserCreate,
    UserUpdate,
)

__all__ = ["User", "UserCreate", "UserUpdate"]
