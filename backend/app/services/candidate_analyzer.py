"""Candidate profile analysis.

Loads and validates the candidate knowledge source (``data/candidate.json``)
into a structured ``CandidateProfile`` and derives interview-relevant signals
(skill gaps, journey-based topics).

Collaborators: candidate.json (data source).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.candidate import CandidateProfile, SkillLevel
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CandidateAnalyzer:
    """Reads and analyzes candidate profiles."""

    def __init__(self, data_dir: Path | None = None) -> None:
        #: Default to backend/app/data unless overridden (useful for tests).
        self._data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data")

    def load_candidate(self, candidate_id: str) -> CandidateProfile:
        """Load and validate a candidate profile from the data directory.

        Placeholder: loads candidate.json and returns the profile. No
        business logic applied yet.
        """
        raw = json.loads((self._data_dir / "candidate.json").read_text(encoding="utf-8"))
        profile = CandidateProfile(**raw)
        logger.info("Loaded candidate profile %s", profile.id)
        return profile

    def derive_skill_gaps(self, profile: CandidateProfile) -> list[str]:
        """Return skills flagged below the expected threshold.

        Placeholder: no analysis implemented yet.
        """
        raise NotImplementedError("Skill-gap analysis will be implemented with interview logic.")

    def suggest_focus_topics(self, profile: CandidateProfile) -> list[str]:
        """Return topics to prioritize based on the learning journey.

        Placeholder: no analysis implemented yet.
        """
        raise NotImplementedError("Focus-topic suggestion will be implemented with interview logic.")
