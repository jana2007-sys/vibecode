"""Question planning.

Decides which question to ask next, given the candidate profile, the current
topic, and the conversation history. This is where adaptation logic will live.

Collaborators: CurriculumLoader, CandidateAnalyzer, MemoryEngine.
"""

from __future__ import annotations

from app.models.curriculum import Curriculum, Topic
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.memory_engine import MemoryEngine
from app.utils.logging import get_logger

logger = get_logger(__name__)


class QuestionPlanner:
    """Selects and orders interview questions."""

    def __init__(
        self,
        curriculum_loader: CurriculumLoader,
        candidate_analyzer: CandidateAnalyzer,
        memory_engine: MemoryEngine,
    ) -> None:
        self._curriculum = curriculum_loader
        self._analyzer = candidate_analyzer
        self._memory = memory_engine

    def first_question_for_topic(self, topic: Topic) -> str:
        """Return the opening question for a topic.

        Placeholder: will adapt question choice to candidate profile and
        learning journey.
        """
        raise NotImplementedError("Question adaptation will be implemented with interview logic.")

    def next_question(self, session_id: str, topic: Topic) -> str:
        """Return the next question within a topic.

        Placeholder: will use conversation history to pick the next question.
        """
        raise NotImplementedError("Question adaptation will be implemented with interview logic.")

    def should_advance_topic(self, session_id: str, topic: Topic) -> bool:
        """Return True when the candidate is ready to move to the next topic.

        Placeholder: will combine evaluation signals with topic coverage.
        """
        raise NotImplementedError("Topic-advance decision will be implemented with interview logic.")
