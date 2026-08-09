"""Idempotent candidate seeding.

Loads the shipped ``data/candidates.json`` knowledge source into the ``candidates``
table so predefined candidates exist before the UI asks for them. Seeding runs on
app startup and is safe to re-run: existing rows are refreshed in place.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.database.repositories.candidate_repository import CandidateRepository
from app.models.common import utc_now
from app.models.candidate import CandidateCreate
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CandidateSeeder:
    """Populates the candidates table from the shipped data file."""

    def __init__(self, candidate_repository: CandidateRepository, data_dir: Path | None = None) -> None:
        self._candidates = candidate_repository
        self._data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data")

    def seed(self) -> int:
        """Upsert every candidate in ``candidates.json``; returns the count."""
        path = self._data_dir / "candidates.json"
        if not path.is_file():
            logger.warning("No candidates seed data at %s; skipping seeding.", path)
            return 0

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Malformed candidates seed data at %s; skipping seeding.", path)
            raise ValueError(f"Malformed candidates seed data: {path}") from exc

        entries = raw.get("candidates", []) if isinstance(raw, dict) else raw
        count = 0
        now = utc_now()
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            if self._candidates.get_by_id(entry["id"]) is not None:
                # Never clobber an existing row (it may carry user edits).
                continue
            profile = CandidateCreate(**{k: v for k, v in entry.items() if k != "id"})
            self._candidates.upsert(
                candidate_id=entry["id"],
                name=profile.name,
                email=profile.email,
                role=profile.role,
                years_of_experience=profile.years_of_experience,
                experience_level=profile.experience_level,
                skills=[skill.model_dump(mode="json") for skill in profile.skills],
                learning_journey=[item.model_dump(mode="json") for item in profile.learning_journey],
                preferred_languages=profile.preferred_languages,
                focus_areas=profile.focus_areas,
                strengths=profile.strengths,
                notes=profile.notes,
                now=now,
            )
            count += 1

        if count:
            logger.info("Seeded %d candidate profile(s).", count)
        return count
