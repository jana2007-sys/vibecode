"""Focused tests for the CandidateAnalyzer service.

Tests load the real ``candidate.json`` shipped with the project, plus synthetic
fixtures written to pytest ``tmp_path`` to exercise error handling and optional
field defaults.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.models.candidate import CandidateAnalysis, CandidateProfile
from app.services.candidate_analyzer import CandidateAnalyzer
from app.utils.errors import NotFoundError, ValidationError

#: The candidate.json shipped with the project (single built-in candidate).
REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"
REAL_CANDIDATE_ID = "candidate-001"


def _write_candidate(tmp_path: Path, payload: object) -> Path:
    """Write ``payload`` as candidate.json into a temp data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    target = data_dir / "candidate.json"

    if isinstance(payload, Path):
        shutil.copy(payload, target)
    else:
        import json

        target.write_text(json.dumps(payload), encoding="utf-8")
    return data_dir


@pytest.fixture()
def analyzer_with_real_data() -> CandidateAnalyzer:
    """Analyzer bound to the project's real candidate.json."""
    return CandidateAnalyzer(data_dir=REAL_DATA_DIR)


@pytest.fixture()
def minimal_candidate() -> dict:
    """A candidate with only the required fields (no optional data)."""
    return {
        "id": "candidate-min",
        "name": "Min Candidate",
        "role": "Backend Engineer",
        "years_of_experience": 1.0,
        "skills": [{"name": "Python", "level": "beginner"}],
        "learning_journey": [],
    }


# --- Real data -------------------------------------------------------------


class TestRealData:
    def test_load_candidate_returns_profile(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        assert isinstance(profile, CandidateProfile)
        assert profile.id == REAL_CANDIDATE_ID
        assert profile.name == "Alex Rivera"
        assert profile.role == "Backend Engineer"
        assert profile.years_of_experience == 2.0

    def test_completed_topics_map_to_journey_titles(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        completed = analyzer_with_real_data.get_completed_topics(profile)
        assert completed == [
            "Python for Everybody",
            "RESTful Blog API",
            "LeetCode / Codewars",
        ]

    def test_skipped_topics_are_empty_when_unknown(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        assert analyzer_with_real_data.get_skipped_topics(profile) == []

    def test_attempts_are_empty_when_unknown(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        assert analyzer_with_real_data.get_attempts(profile) == {}

    def test_strengths_only_include_intermediate_or_advanced(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        strengths = analyzer_with_real_data.get_strengths(profile)
        assert strengths == ["Python (intermediate)", "Django (intermediate)"]

    def test_areas_for_further_assessment_include_beginner_skills(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        areas = analyzer_with_real_data.get_areas_for_further_assessment(profile)
        assert "SQL (beginner)" in areas
        assert "Docker (beginner)" in areas
        assert "System Design (beginner)" in areas

    def test_areas_include_topics_candidate_is_learning_next(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        areas = analyzer_with_real_data.get_areas_for_further_assessment(profile)
        assert "SQL depth and system design" in areas

    def test_derive_skill_gaps_returns_beginner_skill_names(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        gaps = analyzer_with_real_data.derive_skill_gaps(profile)
        assert gaps == ["SQL", "Docker", "System Design"]

    def test_suggest_focus_topics_prioritizes_gaps_and_focus_areas(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        focus = analyzer_with_real_data.suggest_focus_topics(profile)
        assert focus[:3] == ["SQL", "Docker", "System Design"]
        assert "SQL depth and system design" in focus
        assert "Backend API design" in focus
        assert "Databases" in focus
        assert "Testing" in focus

    def test_learning_signals_derived_from_available_data(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        profile = analyzer_with_real_data.load_candidate(REAL_CANDIDATE_ID)
        signals = analyzer_with_real_data.get_learning_signals(profile)
        assert "preferred language: Python" in signals
        assert "focus area: Databases" in signals
        assert any("Prefers practical examples" in s for s in signals)
        assert "has completed project work" in signals
        assert "engages in regular practice" in signals

    def test_analyze_returns_normalized_candidate_analysis(
        self, analyzer_with_real_data: CandidateAnalyzer
    ) -> None:
        analysis = analyzer_with_real_data.analyze(REAL_CANDIDATE_ID)
        assert isinstance(analysis, CandidateAnalysis)
        assert analysis.candidate_id == REAL_CANDIDATE_ID
        assert analysis.profile.id == REAL_CANDIDATE_ID
        assert len(analysis.completed_topics) == 3
        assert analysis.skipped_topics == []
        assert analysis.attempts == {}
        assert len(analysis.strengths) == 2
        assert len(analysis.areas_for_further_assessment) >= 3
        assert analysis.learning_signals


# --- Error handling ---------------------------------------------------------


class TestErrorHandling:
    def test_missing_data_source_raises_not_found(self, tmp_path: Path) -> None:
        analyzer = CandidateAnalyzer(data_dir=tmp_path)
        with pytest.raises(NotFoundError):
            analyzer.load_candidate(REAL_CANDIDATE_ID)

    def test_malformed_json_raises_validation_error(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "candidate.json").write_text("{ not json", encoding="utf-8")
        analyzer = CandidateAnalyzer(data_dir=data_dir)
        with pytest.raises(ValidationError):
            analyzer.load_candidate(REAL_CANDIDATE_ID)

    def test_non_object_root_raises_validation_error(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, [1, 2, 3])
        analyzer = CandidateAnalyzer(data_dir=tmp_path / "data")
        with pytest.raises(ValidationError):
            analyzer.load_candidate(REAL_CANDIDATE_ID)

    def test_schema_mismatch_raises_validation_error(self, tmp_path: Path) -> None:
        _write_candidate(tmp_path, {"id": "x", "skills": "not-a-list"})
        analyzer = CandidateAnalyzer(data_dir=tmp_path / "data")
        with pytest.raises(ValidationError):
            analyzer.load_candidate("x")

    def test_unknown_candidate_raises_not_found(self, tmp_path: Path) -> None:
        data_dir = _write_candidate(tmp_path, REAL_DATA_DIR / "candidate.json")
        analyzer = CandidateAnalyzer(data_dir=data_dir)
        with pytest.raises(NotFoundError):
            analyzer.load_candidate("candidate-999")

    def test_missing_optional_fields_use_defaults(
        self, tmp_path: Path, minimal_candidate: dict
    ) -> None:
        data_dir = _write_candidate(tmp_path, minimal_candidate)
        analyzer = CandidateAnalyzer(data_dir=data_dir)
        profile = analyzer.load_candidate("candidate-min")
        assert profile.preferred_languages == []
        assert profile.focus_areas == []
        assert profile.notes == ""
        assert analyzer.get_completed_topics(profile) == []
        assert analyzer.get_skipped_topics(profile) == []
        assert analyzer.get_attempts(profile) == {}
        assert analyzer.get_learning_signals(profile) == []
        assert analyzer.get_strengths(profile) == []
        assert analyzer.get_areas_for_further_assessment(profile) == ["Python (beginner)"]
