"""Curriculum loading, caching, and read-only access.

Loads and validates the curriculum knowledge source (``data/curriculum.json``)
into a typed ``Curriculum``, caches it for the process lifetime, and exposes a
read-only access layer over its topics and questions.

The shipped curriculum is a flat ``curriculum -> topics -> questions`` document.
It has no explicit "days", "modules", "tools", or "objectives" fields, so the
access layer adapts to the real structure:

- topic indexes act as the curriculum units ("days"),
- learning objectives are derived verbatim from a topic's ``description`` and
  each question's ``expects`` keywords (nothing is invented),
- tool lookups return an empty list because the data defines no tools,
- module lookup is expressed as topic-by-id lookup.

Collaborators: curriculum.json (data source).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from app.models.curriculum import Curriculum, Topic
from app.utils.errors import NotFoundError, ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=8)
def _read_curriculum(data_dir: Path, curriculum_id: str) -> Curriculum:
    """Read, validate, and cache a curriculum for the process lifetime.

    Keyed by ``(data_dir, curriculum_id)`` so repeated loads never re-read the
    file. Exceptions are not cached, so a fixed data file will be retried on
    the next call.
    """
    path = data_dir / "curriculum.json"
    if not path.is_file():
        raise NotFoundError(f"Curriculum data source not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Malformed curriculum data source: {path}") from exc

    if not isinstance(raw, dict):
        raise ValidationError(f"Curriculum data source must be a JSON object: {path}")

    try:
        curriculum = Curriculum(**raw)
    except PydanticValidationError as exc:
        raise ValidationError(
            f"Invalid curriculum data in {path}: {exc.error_count()} validation error(s)"
        ) from exc

    if curriculum.id != curriculum_id:
        raise NotFoundError(f"Curriculum {curriculum_id} not found in {path}")

    return curriculum


class CurriculumLoader:
    """Reads and caches curriculum definitions and provides topic lookup."""

    def __init__(self, data_dir: Path | None = None) -> None:
        #: Default to backend/app/data unless overridden (useful for tests).
        self._data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data")

    # --- Loading / validation -------------------------------------------------

    def load_curriculum(self, curriculum_id: str) -> Curriculum:
        """Load and validate a curriculum by id (cached for the process lifetime).

        Raises:
            NotFoundError: when the curriculum data source is missing or the
                requested curriculum is not present in it.
            ValidationError: when the data source is malformed or does not
                conform to the ``Curriculum`` schema.
        """
        curriculum = _read_curriculum(self._data_dir, curriculum_id)
        logger.info(
            "Loaded curriculum %s (%d topics)",
            curriculum.id,
            len(curriculum.topics),
        )
        return curriculum

    # --- Topic lookup ---------------------------------------------------------

    def get_topic(self, curriculum: Curriculum, topic_index: int) -> Topic | None:
        """Return the topic at the given index, or None when out of range."""
        if 0 <= topic_index < len(curriculum.topics):
            return curriculum.topics[topic_index]
        return None

    def get_topic_at(self, curriculum: Curriculum, topic_index: int) -> Topic:
        """Return the topic at the given index, raising on invalid indexes.

        This is the strict variant of :meth:`get_topic` for callers that want a
        clear error instead of ``None`` for out-of-range or non-integer indexes.
        """
        if not isinstance(topic_index, int) or isinstance(topic_index, bool):
            raise ValidationError(f"Topic index must be an integer, got: {topic_index!r}")
        if not 0 <= topic_index < len(curriculum.topics):
            raise ValidationError(
                f"Topic index {topic_index} out of range for curriculum "
                f"{curriculum.id} (valid range 0..{len(curriculum.topics) - 1})"
            )
        return curriculum.topics[topic_index]

    def get_topic_by_id(self, curriculum: Curriculum, topic_id: str) -> Topic | None:
        """Return the topic whose id matches ``topic_id``, or None.

        Uses an in-memory ``{topic_id: topic}`` index built from the loaded
        curriculum for O(1) lookup.
        """
        return self._index_by_id(curriculum).get(topic_id)

    def is_last_topic(self, curriculum: Curriculum, topic_index: int) -> bool:
        """Return True when the given index is the final topic."""
        return topic_index >= len(curriculum.topics) - 1

    # --- Objectives / tools (per topic, the curriculum's unit) ----------------

    def get_learning_objectives(self, topic: Topic) -> list[str]:
        """Return learning objectives for a topic, derived only from the data.

        Combines the curriculum-authored topic ``description`` with each
        question's ``expects`` keywords (the concepts an ideal answer should
        mention). Nothing is added beyond what the curriculum states.
        """
        objectives: list[str] = []

        description = topic.description.strip()
        if description:
            objectives.append(description)

        for question in topic.questions:
            for keyword in question.expects:
                objective = f"{question.id}: {keyword}"
                if objective not in objectives:
                    objectives.append(objective)

        return objectives

    def get_tools(self, topic: Topic) -> list[str]:
        """Return tools associated with a topic.

        ``curriculum.json`` defines no tool information, so this is always
        empty. Kept as an explicit method so the interview engine has a stable,
        truthful interface to call.
        """
        return []

    # --- Search ---------------------------------------------------------------

    def search(self, curriculum: Curriculum, query: str) -> list[Topic]:
        """Return topics matching ``query`` across id, title, description,
        question text, and question ``expects`` keywords (case-insensitive).

        Empty queries return no matches.
        """
        needle = query.strip().lower()
        if not needle:
            return []

        matches: list[Topic] = []
        for topic in curriculum.topics:
            haystack = " ".join(
                [
                    topic.id,
                    topic.title,
                    topic.description,
                    *[question.text for question in topic.questions],
                    *[keyword for question in topic.questions for keyword in question.expects],
                ]
            ).lower()
            if needle in haystack:
                matches.append(topic)
        return matches

    # --- Overview / available units -------------------------------------------

    def get_all_topics(self, curriculum: Curriculum) -> list[Topic]:
        """Return every topic in the curriculum, in curriculum order."""
        return list(curriculum.topics)

    def get_all_topic_ids(self, curriculum: Curriculum) -> list[str]:
        """Return the ordered list of topic ids in the curriculum."""
        return [topic.id for topic in curriculum.topics]

    def get_topic_count(self, curriculum: Curriculum) -> int:
        """Return the number of topics in the curriculum."""
        return len(curriculum.topics)

    def get_available_days(self, curriculum: Curriculum) -> list[int]:
        """Return the available curriculum units as topic indexes.

        The curriculum has no explicit day numbers; topic indexes serve as the
        day units, so this is ``[0, 1, ..., topic_count - 1]``.
        """
        return list(range(len(curriculum.topics)))

    # --- Internal helpers -----------------------------------------------------

    @staticmethod
    def _index_by_id(curriculum: Curriculum) -> dict[str, Topic]:
        """Build an in-memory ``{topic_id: topic}`` index for fast lookup."""
        return {topic.id: topic for topic in curriculum.topics}
