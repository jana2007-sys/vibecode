"""Curriculum loading and caching.

Loads and validates the curriculum knowledge source (``data/curriculum.json``)
into a typed ``Curriculum`` and caches it for the process lifetime.

Collaborators: curriculum.json (data source).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.models.curriculum import Curriculum, Topic
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CurriculumLoader:
    """Reads and caches curriculum definitions."""

    def __init__(self, data_dir: Path | None = None) -> None:
        #: Default to backend/app/data unless overridden (useful for tests).
        self._data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data")

    def load_curriculum(self, curriculum_id: str) -> Curriculum:
        """Load and validate a curriculum by id.

        Placeholder: returns the single built-in curriculum; multi-curriculum
        lookup will be added with business logic.
        """
        raw = json.loads((self._data_dir / "curriculum.json").read_text(encoding="utf-8"))
        curriculum = Curriculum(**raw)
        logger.info("Loaded curriculum %s (%d topics)", curriculum.id, len(curriculum.topics))
        return curriculum

    def get_topic(self, curriculum: Curriculum, topic_index: int) -> Topic | None:
        """Return the topic at the given index, or None when out of range."""
        if 0 <= topic_index < len(curriculum.topics):
            return curriculum.topics[topic_index]
        return None

    def is_last_topic(self, curriculum: Curriculum, topic_index: int) -> bool:
        """Return True when the given index is the final topic."""
        return topic_index >= len(curriculum.topics) - 1
