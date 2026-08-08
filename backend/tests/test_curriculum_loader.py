"""Focused tests for the CurriculumLoader service.

Tests load the real ``curriculum.json`` shipped with the project, plus synthetic
fixtures written to pytest ``tmp_path`` to exercise error handling, optional
field defaults, and the in-memory cache.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.models.curriculum import Curriculum, Topic
from app.services.curriculum_loader import CurriculumLoader
from app.utils.errors import NotFoundError, ValidationError

#: The curriculum.json shipped with the project (single built-in curriculum).
REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
REAL_CURRICULUM_ID = "curriculum-001"


def _write_curriculum(tmp_path: Path, payload: object) -> Path:
    """Write ``payload`` as curriculum.json into a temp data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    target = data_dir / "curriculum.json"

    if isinstance(payload, Path):
        shutil.copy(payload, target)
    else:
        target.write_text(json.dumps(payload), encoding="utf-8")
    return data_dir


@pytest.fixture()
def loader_with_real_data() -> CurriculumLoader:
    """Loader bound to the project's real curriculum.json."""
    return CurriculumLoader(data_dir=REAL_DATA_DIR)


@pytest.fixture()
def real_curriculum(loader_with_real_data: CurriculumLoader) -> Curriculum:
    """The project's real curriculum loaded once."""
    return loader_with_real_data.load_curriculum(REAL_CURRICULUM_ID)


@pytest.fixture()
def minimal_curriculum() -> dict:
    """A curriculum with only the required fields (no optional data)."""
    return {"id": "curriculum-min", "title": "Minimal Curriculum"}


# --- Real data -------------------------------------------------------------


class TestRealData:
    def test_load_curriculum_succeeds(self, loader_with_real_data: CurriculumLoader) -> None:
        curriculum = loader_with_real_data.load_curriculum(REAL_CURRICULUM_ID)
        assert isinstance(curriculum, Curriculum)
        assert curriculum.id == REAL_CURRICULUM_ID
        assert curriculum.title == "Full-Stack Engineering Interview Path"
        assert curriculum.version == "1.0.0"
        assert len(curriculum.topics) == 3

    def test_valid_day_lookup(self, real_curriculum: Curriculum) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        assert loader.get_topic(real_curriculum, 0) is real_curriculum.topics[0]
        assert loader.get_topic_at(real_curriculum, 2).id == "topic-systems"
        assert loader.get_available_days(real_curriculum) == [0, 1, 2]

    def test_invalid_day_lookup_returns_none(
        self, real_curriculum: Curriculum
    ) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        assert loader.get_topic(real_curriculum, -1) is None
        assert loader.get_topic(real_curriculum, 99) is None

    def test_invalid_day_lookup_raises(
        self, real_curriculum: Curriculum
    ) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        for bad in (-1, 3, 99):
            with pytest.raises(ValidationError):
                loader.get_topic_at(real_curriculum, bad)
        with pytest.raises(ValidationError):
            loader.get_topic_at(real_curriculum, "one")
        with pytest.raises(ValidationError):
            loader.get_topic_at(real_curriculum, True)

    def test_module_lookup_via_topic_id(self, real_curriculum: Curriculum) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        topic = loader.get_topic_by_id(real_curriculum, "topic-databases")
        assert isinstance(topic, Topic)
        assert topic.title == "Databases & SQL"
        assert loader.get_topic_by_id(real_curriculum, "topic-missing") is None

    def test_objective_retrieval(self, real_curriculum: Curriculum) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        python = loader.get_topic_by_id(real_curriculum, "topic-python")
        assert python is not None
        objectives = loader.get_learning_objectives(python)
        assert "Data structures, comprehensions, typing, and common idioms." in objectives
        assert "py-001: immutable" in objectives
        assert "py-001: hashable" in objectives
        assert "py-002: global interpreter lock" in objectives

    def test_tool_retrieval_is_empty(self, real_curriculum: Curriculum) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        assert loader.get_tools(real_curriculum.topics[0]) == []

    def test_keyword_search(self, real_curriculum: Curriculum) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        assert [t.id for t in loader.search(real_curriculum, "python")] == ["topic-python"]
        assert [t.id for t in loader.search(real_curriculum, "B-tree")] == ["topic-databases"]
        assert [t.id for t in loader.search(real_curriculum, "URL")] == ["topic-systems"]
        assert [t.id for t in loader.search(real_curriculum, "immutable")] == ["topic-python"]
        assert loader.search(real_curriculum, "PythOn")[0].id == "topic-python"
        assert loader.search(real_curriculum, "") == []
        assert loader.search(real_curriculum, "   ") == []
        assert loader.search(real_curriculum, "zzzz-not-in-curriculum") == []

    def test_all_days_retrieval(self, real_curriculum: Curriculum) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        assert [t.id for t in loader.get_all_topics(real_curriculum)] == [
            "topic-python",
            "topic-databases",
            "topic-systems",
        ]
        assert loader.get_all_topic_ids(real_curriculum) == [
            "topic-python",
            "topic-databases",
            "topic-systems",
        ]
        assert loader.get_topic_count(real_curriculum) == 3

    def test_is_last_topic(self, real_curriculum: Curriculum) -> None:
        loader = CurriculumLoader(data_dir=REAL_DATA_DIR)
        assert not loader.is_last_topic(real_curriculum, 0)
        assert loader.is_last_topic(real_curriculum, 2)

    def test_load_is_cached_without_rereading(
        self, loader_with_real_data: CurriculumLoader
    ) -> None:
        first = loader_with_real_data.load_curriculum(REAL_CURRICULUM_ID)
        second = loader_with_real_data.load_curriculum(REAL_CURRICULUM_ID)
        assert first is second


# --- Error handling ---------------------------------------------------------


class TestErrorHandling:
    def test_missing_data_source_raises_not_found(self, tmp_path: Path) -> None:
        loader = CurriculumLoader(data_dir=tmp_path)
        with pytest.raises(NotFoundError):
            loader.load_curriculum(REAL_CURRICULUM_ID)

    def test_malformed_json_raises_validation_error(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "curriculum.json").write_text("{ not json", encoding="utf-8")
        loader = CurriculumLoader(data_dir=data_dir)
        with pytest.raises(ValidationError):
            loader.load_curriculum(REAL_CURRICULUM_ID)

    def test_non_object_root_raises_validation_error(self, tmp_path: Path) -> None:
        _write_curriculum(tmp_path, ["a", "b"])
        loader = CurriculumLoader(data_dir=tmp_path / "data")
        with pytest.raises(ValidationError):
            loader.load_curriculum(REAL_CURRICULUM_ID)

    def test_schema_mismatch_raises_validation_error(self, tmp_path: Path) -> None:
        _write_curriculum(tmp_path, {"id": "x", "title": "X", "topics": "not-a-list"})
        loader = CurriculumLoader(data_dir=tmp_path / "data")
        with pytest.raises(ValidationError):
            loader.load_curriculum("x")

    def test_unknown_curriculum_id_raises_not_found(self, tmp_path: Path) -> None:
        data_dir = _write_curriculum(tmp_path, REAL_DATA_DIR / "curriculum.json")
        loader = CurriculumLoader(data_dir=data_dir)
        with pytest.raises(NotFoundError):
            loader.load_curriculum("curriculum-999")

    def test_missing_optional_fields_use_defaults(
        self, tmp_path: Path, minimal_curriculum: dict
    ) -> None:
        data_dir = _write_curriculum(tmp_path, minimal_curriculum)
        loader = CurriculumLoader(data_dir=data_dir)
        curriculum = loader.load_curriculum("curriculum-min")
        assert curriculum.description == ""
        assert curriculum.version == "1.0.0"
        assert curriculum.topics == []
        assert loader.get_all_topics(curriculum) == []
        assert loader.get_topic_count(curriculum) == 0
        assert loader.get_available_days(curriculum) == []
        assert loader.search(curriculum, "anything") == []
