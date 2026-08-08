"""Candidate profile analysis.

Loads and validates the candidate knowledge source (``data/candidate.json``)
into a structured ``CandidateProfile`` and derives interview-relevant signals
(completed/skipped topics, attempts, strengths, and areas for further
assessment) strictly from the available candidate data.

The analyzer is independent of any LLM: everything here is deterministic,
rule-based derivation from the candidate JSON.

Collaborators: candidate.json (data source).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from app.models.candidate import CandidateAnalysis, CandidateProfile
from app.utils.errors import NotFoundError, ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Self-reported skill levels that count as a demonstrated strength.
_STRENGTH_LEVELS = {"intermediate", "advanced"}
#: Self-reported skill levels that flag an area needing further assessment.
_GAP_LEVELS = {"beginner"}
#: Generic sentence separators used to split free-text ``notes``.
_NOTE_SEPARATORS = re.compile(r"[.;]\s*")


class CandidateAnalyzer:
    """Reads and analyzes candidate profiles.

    All derivation methods are pure functions of a validated
    ``CandidateProfile`` and never fabricate data that is absent from the
    candidate JSON.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        #: Default to backend/app/data unless overridden (useful for tests).
        self._data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data")

    # --- Loading / validation -------------------------------------------------

    def load_candidate(self, candidate_id: str) -> CandidateProfile:
        """Load and validate a candidate profile from the data directory.

        Raises:
            NotFoundError: when the candidate data source is missing or the
                requested candidate is not present in it.
            ValidationError: when the data source is malformed or does not
                conform to the ``CandidateProfile`` schema.
        """
        path = self._data_dir / "candidate.json"
        if not path.is_file():
            raise NotFoundError(f"Candidate data source not found: {path}")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Malformed candidate data source: {path}") from exc

        if not isinstance(raw, dict):
            raise ValidationError(f"Candidate data source must be a JSON object: {path}")

        try:
            profile = CandidateProfile(**raw)
        except PydanticValidationError as exc:
            raise ValidationError(
                f"Invalid candidate data in {path}: {exc.error_count()} validation error(s)"
            ) from exc

        if profile.id != candidate_id:
            raise NotFoundError(f"Candidate {candidate_id} not found in {path}")

        logger.info("Loaded candidate profile %s", profile.id)
        return profile

    # --- Missions / topics ----------------------------------------------------

    def get_completed_topics(self, profile: CandidateProfile) -> list[str]:
        """Return the missions/topics the candidate has completed.

        Maps each ``learning_journey`` entry to its title. Absent entries are
        simply not listed; nothing is inferred.
        """
        return [entry.title for entry in profile.learning_journey]

    def get_skipped_topics(self, profile: CandidateProfile) -> list[str]:
        """Return missions/topics the candidate skipped.

        ``candidate.json`` carries no skipped-topic information, so this is
        always empty. Kept as an explicit method so the interview engine has a
        stable, truthful interface to call.
        """
        return []

    def get_attempts(self, profile: CandidateProfile) -> dict[str, int]:
        """Return topic/subject attempt counts.

        ``candidate.json`` carries no attempt-count information, so this is
        always empty. Kept as an explicit method so the interview engine has a
        stable, truthful interface to call.
        """
        return {}

    # --- Derived analysis -----------------------------------------------------

    def get_learning_signals(self, profile: CandidateProfile) -> list[str]:
        """Return learning signals derived only from the available profile data."""
        signals: list[str] = []

        for language in profile.preferred_languages:
            signals.append(f"preferred language: {language}")

        for area in profile.focus_areas:
            signals.append(f"focus area: {area}")

        signals.extend(
            fragment.strip() for fragment in _NOTE_SEPARATORS.split(profile.notes) if fragment.strip()
        )

        if any(entry.type == "project" for entry in profile.learning_journey):
            signals.append("has completed project work")

        if any(entry.type == "practice" for entry in profile.learning_journey):
            signals.append("engages in regular practice")

        return signals

    def derive_skill_gaps(self, profile: CandidateProfile) -> list[str]:
        """Return skills self-reported below the expected threshold (beginner)."""
        return [
            skill.name
            for skill in profile.skills
            if skill.level.strip().lower() in _GAP_LEVELS
        ]

    def get_strengths(self, profile: CandidateProfile) -> list[str]:
        """Return candidate strengths based ONLY on the available profile data.

        Strengths are the self-reported skills at intermediate/advanced level.
        """
        return [
            f"{skill.name} ({skill.level})"
            for skill in profile.skills
            if skill.level.strip().lower() in _STRENGTH_LEVELS
        ]

    def get_areas_for_further_assessment(self, profile: CandidateProfile) -> list[str]:
        """Return topics that may need further assessment, based ONLY on the data.

        Combines beginner-level skills with topics the candidate states they are
        learning next in the free-text notes (e.g. "learning X next").
        """
        areas: list[str] = [
            f"{skill.name} ({skill.level})"
            for skill in profile.skills
            if skill.level.strip().lower() in _GAP_LEVELS
        ]

        for match in re.finditer(r"learning\s+([^.;]+?)\s+next", profile.notes, flags=re.IGNORECASE):
            topic = match.group(1).strip().rstrip(".")
            if topic and topic not in areas:
                areas.append(topic)

        return areas

    def suggest_focus_topics(self, profile: CandidateProfile) -> list[str]:
        """Return topics to prioritize based on the learning journey.

        Prioritizes beginner-level skills, topics the candidate is learning
        next, and declared focus areas (deduplicated, order-preserving).
        """
        focus: list[str] = []

        for skill in profile.skills:
            if skill.level.strip().lower() in _GAP_LEVELS and skill.name not in focus:
                focus.append(skill.name)

        for match in re.finditer(r"learning\s+([^.;]+?)\s+next", profile.notes, flags=re.IGNORECASE):
            topic = match.group(1).strip().rstrip(".")
            if topic and topic not in focus:
                focus.append(topic)

        for area in profile.focus_areas:
            if area not in focus:
                focus.append(area)

        return focus

    # --- Normalized analysis --------------------------------------------------

    def analyze_profile(self, profile: CandidateProfile) -> CandidateAnalysis:
        """Assemble a normalized ``CandidateAnalysis`` from a validated profile.

        This is the primary entry point for collaborators such as
        ``QuestionPlanner`` and the interactive ``InterviewEngine``: it turns an
        already-loaded profile into every derived dimension in a single
        validated object.
        """
        analysis = CandidateAnalysis(
            candidate_id=profile.id,
            profile=profile,
            completed_topics=self.get_completed_topics(profile),
            skipped_topics=self.get_skipped_topics(profile),
            attempts=self.get_attempts(profile),
            learning_signals=self.get_learning_signals(profile),
            strengths=self.get_strengths(profile),
            areas_for_further_assessment=self.get_areas_for_further_assessment(profile),
        )
        logger.info(
            "Analyzed candidate %s (%d strengths, %d focus areas)",
            profile.id,
            len(analysis.strengths),
            len(analysis.areas_for_further_assessment),
        )
        return analysis

    def analyze(self, candidate_id: str) -> CandidateAnalysis:
        """Produce the normalized analysis object for the interview engine.

        This is the primary entry point for collaborators such as
        ``QuestionPlanner``: it loads the candidate once and assembles every
        derived dimension into a single validated ``CandidateAnalysis``.
        """
        profile = self.load_candidate(candidate_id)
        return self.analyze_profile(profile)
