"""CRUD module - Re-exports for backward compatibility.

This module re-exports CRUD operations from core.crud for
backward compatibility with existing code that imports from app.crud.
"""

from app.core.crud import *  # noqa: F401, F403