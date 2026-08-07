"""Reusable primitives shared across all models.

Centralizing ID and timestamp conventions keeps the API contracts consistent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


def new_uuid() -> str:
    """Generate a new server-side UUID string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


Id = Annotated[str, Field(min_length=1, max_length=64)]
"""Short alias for identifier fields (UUID or slug strings)."""


class BaseModelConfig(BaseModel):
    """Common Pydantic configuration for all API models."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        use_enum_values=True,
    )
