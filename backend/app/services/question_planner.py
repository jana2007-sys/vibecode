"""Question planning.

Builds a deterministic, personalized interview plan from the candidate analysis
and the curriculum. Every planned question is grounded in a curriculum question
template (no invented text), and the plan guarantees a minimum of 8 questions
covering at least 4 distinct curriculum topics.

Planning is fully deterministic: given the same candidate analysis and
curriculum it always produces the same plan. Gemini-based adaptive planning will
be layered on later; nothing here calls an LLM.

Collaborators: CurriculumLoader, CandidateAnalyzer, MemoryEngine (unused for
planning; kept for the future interactive engine).
"""

from __future__ import annotations

import re
from collections import Counter

from app.models.candidate import CandidateAnalysis
from app.models.curriculum import Curriculum, InterviewPlan, PlannedQuestion, Topic
from app.models.curriculum import QuestionTemplate
from app.services.candidate_analyzer import CandidateAnalyzer
from app.services.curriculum_loader import CurriculumLoader
from app.services.memory_engine import MemoryEngine
from app.utils.errors import ValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Guarantees enforced by every plan.
MIN_QUESTIONS = 8
MIN_TOPICS = 4

#: Difficulty tiers present in the curriculum, low -> high.
_DIFFICULTY_RANKS = {"easy": 0, "medium": 1, "hard": 2}
_DIFFICULTY_ORDER = ("easy", "medium", "hard")

#: Low-information words ignored when matching candidate signals to topics.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "is",
        "it", "of", "on", "or", "that", "the", "this", "to", "with", "vs",
    }
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Return the normalized lowercase alphanumeric tokens of ``text``."""
    return set(_TOKEN_PATTERN.findall(text.lower()))


class QuestionPlanner:
    """Selects and orders interview questions into a personalized plan."""

    def __init__(
        self,
        curriculum_loader: CurriculumLoader,
        candidate_analyzer: CandidateAnalyzer,
        memory_engine: MemoryEngine | None = None,
    ) -> None:
        self._curriculum = curriculum_loader
        self._analyzer = candidate_analyzer
        self._memory = memory_engine

    # --- Plan generation ------------------------------------------------------

    def create_plan(self, candidate_id: str, curriculum_id: str) -> InterviewPlan:
        """Build a personalized plan for a candidate against a curriculum.

        Loads the curriculum and the candidate analysis, then delegates to
        :meth:`plan_for`.
        """
        curriculum = self._curriculum.load_curriculum(curriculum_id)
        analysis = self._analyzer.analyze(candidate_id)
        return self.plan_for(analysis, curriculum)

    def plan_for(self, analysis: CandidateAnalysis, curriculum: Curriculum) -> InterviewPlan:
        """Build a plan from an already-validated analysis and curriculum.

        Raises:
            ValidationError: when the curriculum has fewer than 4 usable topics
                (topics with questions) or fewer than 8 available questions, so
                the plan never fakes coverage it cannot back with real content.
        """
        usable = [topic for topic in curriculum.topics if topic.questions]
        if len(usable) < MIN_TOPICS:
            raise ValidationError(
                f"Curriculum {curriculum.id} has {len(usable)} topic(s) with questions; "
                f"at least {MIN_TOPICS} usable topics are required to build a plan"
            )

        available = sum(len(topic.questions) for topic in usable)
        if available < MIN_QUESTIONS:
            raise ValidationError(
                f"Curriculum {curriculum.id} offers {available} question(s); "
                f"at least {MIN_QUESTIONS} are required to build a plan"
            )

        ranked = self._rank_topics(analysis, usable)
        ordered, skipped_ids = self._order_for_skipped(analysis, ranked)
        selected = self._select_questions(ordered, skipped_ids)

        questions = [
            PlannedQuestion(
                sequence=sequence,
                topic_id=topic.id,
                curriculum_question_id=question.id,
                text=question.text,
                difficulty=question.difficulty,
                expects=list(question.expects),
                question_type=self._question_type(question),
                follow_up_allowed=sequence < len(selected),
            )
            for sequence, (topic, question) in enumerate(selected, start=1)
        ]

        covered = list(dict.fromkeys(question.topic_id for question in questions))
        return InterviewPlan(
            candidate_id=analysis.candidate_id,
            curriculum_id=curriculum.id,
            total_questions=len(questions),
            topics_covered=covered,
            questions=questions,
        )

    # --- Personalization ------------------------------------------------------

    def _rank_topics(self, analysis: CandidateAnalysis, topics: list[Topic]) -> list[Topic]:
        """Rank topics by relevance to the candidate (stable, descending).

        Higher-scoring topics are prioritized for primary assessment: topics the
        candidate completed, topics with weaker learning signals or more
        attempts, and topics whose content overlaps the candidate's skills,
        focus areas, and assessment areas.
        """
        keywords = self._candidate_keywords(analysis)

        def score(topic: Topic) -> float:
            tokens = _tokenize(f"{topic.id} {topic.title} {topic.description}")
            return sum(keywords.get(token, 0.0) for token in tokens)

        return sorted(topics, key=score, reverse=True)

    def _candidate_keywords(self, analysis: CandidateAnalysis) -> dict[str, float]:
        """Build candidate-topic keyword weights from the analysis fields."""
        keywords: dict[str, float] = {}

        def add(text: str, weight: float) -> None:
            for token in _tokenize(text):
                if token in _STOPWORDS:
                    continue
                keywords[token] = keywords.get(token, 0.0) + weight

        for skill in analysis.profile.skills:
            add(skill.name, 2.0)
            if skill.level.strip().lower() == "beginner":
                add(skill.name, 1.0)

        for title in analysis.completed_topics:
            add(title, 1.0)

        for subject, count in analysis.attempts.items():
            add(subject, 1.0 + 0.5 * max(0, min(count, 5)))

        for area in analysis.areas_for_further_assessment:
            add(area, 1.5)

        for signal in analysis.learning_signals:
            add(signal, 1.0)

        return keywords

    def _order_for_skipped(
        self, analysis: CandidateAnalysis, ranked: list[Topic]
    ) -> list[Topic]:
        """Move explicitly skipped topics to the end of the priority order.

        Skipped areas are never used as primary assessment; they only appear if
        coverage requires them, and always after every non-skipped topic.
        """
        skipped = [topic for topic in ranked if _matches_skipped(topic, analysis.skipped_topics)]
        if not skipped:
            return ranked, set()
        primary = [topic for topic in ranked if topic not in skipped]
        logger.info("Deprioritizing skipped topics: %s", sorted(topic.id for topic in skipped))
        return primary + skipped, {topic.id for topic in skipped}

    # --- Question selection ---------------------------------------------------

    def _select_questions(
        self, ordered: list[Topic], skipped_ids: set[str]
    ) -> list[tuple[Topic, QuestionTemplate]]:
        """Select exactly MIN_QUESTIONS grounded questions.

        Strategy:
          1. coverage pass — the easiest available question from every topic, so
             distinct topics are covered before anything is repeated. Explicitly
             skipped topics are excluded from coverage when enough non-skipped
             topics remain, so skipped areas are only revisited if they are
             genuinely required to build the plan;
          2. fill pass — remaining questions in difficulty-tier order
             (easy -> medium -> hard) across the topic priority order;
          3. variety guards — when the curriculum provides medium or hard
             questions, ensure at least one of each is present, swapping a
             late non-unique-topic question for the missing tier so the harder
             question lands near the end (realistic progression).
        """
        selected: list[tuple[Topic, QuestionTemplate]] = []
        used: set[str] = set()

        non_skipped = [topic for topic in ordered if topic.id not in skipped_ids]
        include_skipped = len(non_skipped) < MIN_TOPICS

        for topic in ordered:
            if topic.id in skipped_ids and not include_skipped:
                continue
            question = self._easiest_available(topic, used)
            if question is not None:
                selected.append((topic, question))
                used.add(question.id)

        for tier in _DIFFICULTY_ORDER:
            tier_rank = _DIFFICULTY_RANKS[tier]
            for topic in ordered:
                if topic.id in skipped_ids and not include_skipped:
                    continue
                for question in topic.questions:
                    if question.id in used or self._difficulty_rank(question.difficulty) != tier_rank:
                        continue
                    selected.append((topic, question))
                    used.add(question.id)
                    if len(selected) >= MIN_QUESTIONS:
                        break
                if len(selected) >= MIN_QUESTIONS:
                    break
            if len(selected) >= MIN_QUESTIONS:
                break

        self._ensure_tier("medium", selected, ordered, used)
        self._ensure_tier("hard", selected, ordered, used)

        return selected[:MIN_QUESTIONS]

    def _easiest_available(
        self, topic: Topic, used: set[str]
    ) -> QuestionTemplate | None:
        """Return the topic's easiest unused question (easy < medium < hard)."""
        best: QuestionTemplate | None = None
        best_rank = len(_DIFFICULTY_ORDER) + 1
        for question in topic.questions:
            if question.id in used:
                continue
            rank = self._difficulty_rank(question.difficulty)
            if rank < best_rank:
                best, best_rank = question, rank
        return best

    def _ensure_tier(
        self,
        tier: str,
        selected: list[tuple[Topic, QuestionTemplate]],
        ordered: list[Topic],
        used: set[str],
    ) -> None:
        """Guarantee at least one question of ``tier`` when the data allows it."""
        rank = _DIFFICULTY_RANKS[tier]
        if any(self._difficulty_rank(question.difficulty) == rank for _, question in selected):
            return

        replacement: tuple[Topic, QuestionTemplate] | None = None
        for topic in ordered:
            for question in topic.questions:
                if question.id not in used and self._difficulty_rank(question.difficulty) == rank:
                    replacement = (topic, question)
                    break
            if replacement is not None:
                break
        if replacement is None:
            return

        counts = Counter(topic.id for topic, _ in selected)
        for index in range(len(selected) - 1, -1, -1):
            topic, question = selected[index]
            if counts[topic.id] <= 1:
                continue
            selected.pop(index)
            used.discard(question.id)
            selected.append(replacement)
            used.add(replacement[1].id)
            return

    # --- Helpers --------------------------------------------------------------

    def _difficulty_rank(self, difficulty: str) -> int:
        """Map a curriculum difficulty label to its tier rank (unknown -> medium)."""
        return _DIFFICULTY_RANKS.get(difficulty.strip().lower(), _DIFFICULTY_RANKS["medium"])

    def _question_type(self, question: QuestionTemplate) -> str:
        """Derive a deterministic question type from the curriculum question text."""
        text = question.text.lower()
        if "design" in text:
            return "architecture"
        if "difference" in text or " vs " in text or text.startswith("compare"):
            return "comparison"
        if any(keyword in text for keyword in ("what happens if", "debug", "troubleshoot", "error")):
            return "troubleshooting"
        if text.startswith(("explain", "describe", "define", "what is", "how does", "how do")):
            return "explanation"
        if any(keyword in text for keyword in ("scenario", "what would you", "how would you", "when would you")):
            return "scenario"
        return "conceptual"

    # --- Interactive engine placeholders (future) ------------------------------

    def first_question_for_topic(self, topic: Topic) -> str:
        """Return the opening question for a topic.

        Placeholder: will adapt question choice to candidate profile and
        learning journey once the interactive InterviewEngine is implemented.
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


def _matches_skipped(topic: Topic, skipped_topics: list[str]) -> bool:
    """Return True when ``topic`` corresponds to an explicitly skipped area.

    Matches by topic id, exact title, or full token overlap between the skipped
    label and the topic's title/description.
    """
    topic_tokens = _tokenize(f"{topic.title} {topic.description}")
    for label in skipped_topics:
        if label == topic.id or label == topic.title:
            return True
        label_tokens = _tokenize(label)
        if label_tokens and label_tokens <= topic_tokens:
            return True
    return False
