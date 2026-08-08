"""Question planning.

Builds a deterministic, personalized interview plan from the candidate analysis
and the curriculum. The curriculum is a question bank of grounded templates (no
invented text): the planner selects an 8-question plan from that bank, so no
candidate is ever asked the whole bank. A complete plan guarantees a minimum of
8 questions covering at least 4 distinct curriculum topics. In development mode
the minimums are waived only for in-progress curricula that offer fewer than 8
questions, allowing partial plans to be previewed; such plans are flagged via
``InterviewPlan.is_complete`` and ``completeness_metadata``.

Planning is fully deterministic: given the same candidate analysis and
curriculum it always produces the same plan. Gemini-based adaptive planning will
be layered on later; nothing here calls an LLM.

Collaborators: CurriculumLoader, CandidateAnalyzer, MemoryEngine (unused for
planning; kept for the future interactive engine).
"""

from __future__ import annotations

import hashlib
import math
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

#: Candidate ids in this namespace are user-created profiles (frontend "Create
#: your profile"). Only they may tune the plan's difficulty mix.
CUSTOM_PROFILE_PREFIX = "custom-"

#: Custom-profile experience level -> difficulty bias. ``mid`` is the default
#: and stays balanced; junior leans easy, senior leans hard.
_EXPERIENCE_TO_BIAS = {"junior": "easy", "mid": None, "senior": "hard"}

#: How strongly a self-reported skill level pulls matching topics forward.
#: Beginner-level skills are primary assessment targets; intermediate/advanced
#: skills still pull their topics forward so the interview probes real
#: experience, but with less weight than an explicit gap.
_SKILL_LEVEL_WEIGHTS = {"beginner": 3.0, "intermediate": 2.0, "advanced": 1.5, "unknown": 1.0}

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


def _stable_hash(*parts: str) -> int:
    """Deterministic 64-bit hash, stable across runs and processes.

    ``hash()`` is randomized per process via ``PYTHONHASHSEED``, so it is never
    used to derive plan variety: the same candidate must produce the same plan
    on every process and machine.
    """
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _prefix_match(left: str, right: str) -> bool:
    """Return True when one token is a prefix of the other (or they are equal).

    Single-character tokens only match exactly, so a keyword like "c" does not
    sweep up unrelated words.
    """
    if left == right:
        return True
    if len(left) < 2 or len(right) < 2:
        return False
    return left.startswith(right) or right.startswith(left)


class QuestionPlanner:
    """Selects and orders interview questions into a personalized plan."""

    def __init__(
        self,
        curriculum_loader: CurriculumLoader,
        candidate_analyzer: CandidateAnalyzer,
        memory_engine: MemoryEngine | None = None,
        *,
        development_mode: bool = False,
    ) -> None:
        """Wire collaborators and planning mode.

        ``development_mode`` disables the production minimums (at least
        ``MIN_TOPICS`` usable topics and ``MIN_QUESTIONS`` available questions),
        allowing partial plans for in-progress curricula. Partial plans are
        flagged via ``InterviewPlan.is_complete`` and ``completeness_metadata``.
        """
        self._curriculum = curriculum_loader
        self._analyzer = candidate_analyzer
        self._memory = memory_engine
        self._development_mode = development_mode

    # --- Plan generation ------------------------------------------------------

    def create_plan(self, candidate_id: str, curriculum_id: str) -> InterviewPlan:
        """Build a personalized plan for a candidate against a curriculum.

        Loads the curriculum and the candidate analysis, then delegates to
        :meth:`plan_for`.
        """
        curriculum = self._curriculum.load_curriculum(curriculum_id)
        analysis = self._analyzer.analyze(candidate_id)
        return self.plan_for(analysis, curriculum)

    def plan_for(
        self,
        analysis: CandidateAnalysis,
        curriculum: Curriculum,
        *,
        development_mode: bool | None = None,
        variety_seed: str | None = None,
    ) -> InterviewPlan:
        """Build a plan from an already-validated analysis and curriculum.

        The curriculum is a question bank: plans always contain at most
        ``MIN_QUESTIONS`` grounded primary questions (never the whole bank), so
        every candidate is asked exactly ``MIN_QUESTIONS`` questions when the
        bank offers at least that many. In production mode (the default) the
        curriculum must support a complete plan: at least ``MIN_TOPICS`` usable
        topics (topics with questions) and ``MIN_QUESTIONS`` available questions.
        In development mode those minimums are waived so in-progress curricula
        can be previewed — but only when fewer than ``MIN_QUESTIONS`` questions
        are available; a full bank is still capped at ``MIN_QUESTIONS``. Partial
        plans are marked ``is_complete=False`` with metadata describing the
        shortfall.

        ``variety_seed`` rotates *which* questions are drawn from the bank so
        different candidates receive different questions even when their
        profiles overlap. The rotation is fully deterministic: the same
        ``(analysis, curriculum, variety_seed)`` always yields the same plan.
        When ``variety_seed`` is ``None`` it defaults to the candidate id, so a
        candidate's plan is stable across sessions and machines while two
        candidates (with different ids) get distinct question decks.

        Args:
            development_mode: per-call override of the constructor default;
                ``None`` (the default) keeps the constructor setting.
            variety_seed: per-call override of the candidate-derived deck seed;
                ``None`` (the default) derives it from ``analysis.candidate_id``.

        Raises:
            ValidationError: in production mode, when the curriculum has fewer
                than ``MIN_TOPICS`` usable topics or fewer than ``MIN_QUESTIONS``
                available questions, so the plan never fakes coverage it cannot
                back with real content.
        """
        if development_mode is None:
            development_mode = self._development_mode
        if variety_seed is None:
            variety_seed = analysis.candidate_id

        usable = [topic for topic in curriculum.topics if topic.questions]
        available = sum(len(topic.questions) for topic in usable)
        if not development_mode:
            self._validate_requirements(curriculum.id, usable, available)

        keywords = self._candidate_keywords(analysis)
        ranked = self._rank_topics(analysis, usable, keywords)
        ordered, skipped_ids = self._order_for_skipped(analysis, ranked)
        # The curriculum is a question bank: the interview always asks at most
        # MIN_QUESTIONS primary questions, never the whole bank. Development mode
        # only waives the minimums for in-progress curricula (fewer than 8
        # questions available), previewing every question such a curriculum
        # offers. A full bank is always capped at MIN_QUESTIONS.
        target_count = (
            None if development_mode and available < MIN_QUESTIONS else MIN_QUESTIONS
        )
        difficulty_bias = self._difficulty_bias(analysis)
        selected = self._select_questions(
            ordered,
            skipped_ids,
            target_count,
            keywords,
            difficulty_bias=difficulty_bias,
            variety_seed=variety_seed,
        )
        logger.debug(
            "Selected questions for candidate %s: %s",
            analysis.candidate_id,
            " > ".join(f"{question.id}({topic.id})" for topic, question in selected),
        )

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
        is_complete, completeness_metadata = self._completeness(
            curriculum.id, questions, covered
        )
        return InterviewPlan(
            candidate_id=analysis.candidate_id,
            curriculum_id=curriculum.id,
            total_questions=len(questions),
            difficulty_bias=difficulty_bias,
            topics_covered=covered,
            is_complete=is_complete,
            completeness_metadata=completeness_metadata,
            questions=questions,
        )

    def _validate_requirements(
        self, curriculum_id: str, usable: list[Topic], available: int
    ) -> None:
        """Raise unless the curriculum can support a complete plan.

        Reports every shortfall at once so a single error explains all missing
        requirements.
        """
        if len(usable) >= MIN_TOPICS and available >= MIN_QUESTIONS:
            return
        shortfalls = []
        if len(usable) < MIN_TOPICS:
            shortfalls.append(
                f"{len(usable)} usable topic(s) present; "
                f"at least {MIN_TOPICS} usable topics are required to build a plan"
            )
        if available < MIN_QUESTIONS:
            shortfalls.append(
                f"{available} question(s) offered; "
                f"at least {MIN_QUESTIONS} are required to build a plan"
            )
        raise ValidationError(f"Curriculum {curriculum_id}: " + "; ".join(shortfalls))

    def _completeness(
        self,
        curriculum_id: str,
        questions: list[PlannedQuestion],
        covered: list[str],
    ) -> tuple[bool, dict[str, object]]:
        """Report whether a plan meets production minimums and why not."""
        missing_topics = max(0, MIN_TOPICS - len(set(covered)))
        missing_questions = max(0, MIN_QUESTIONS - len(questions))
        is_complete = missing_topics == 0 and missing_questions == 0
        if is_complete:
            reason = "Meets production minimums (at least 8 questions across 4 topics)."
        else:
            shortfalls = []
            if missing_topics:
                shortfalls.append(f"needs {missing_topics} more distinct topic(s)")
            if missing_questions:
                shortfalls.append(f"needs {missing_questions} more question(s)")
            reason = "Plan is incomplete; " + " and ".join(shortfalls)
        return is_complete, {
            "curriculum_id": curriculum_id,
            "missing_topics": missing_topics,
            "missing_questions": missing_questions,
            "reason": reason,
        }

    # --- Personalization ------------------------------------------------------

    def _rank_topics(
        self,
        analysis: CandidateAnalysis,
        topics: list[Topic],
        keywords: dict[str, float] | None = None,
    ) -> list[Topic]:
        """Rank topics by relevance to the candidate (stable, descending).

        Higher-scoring topics are prioritized for primary assessment: topics the
        candidate completed, topics with weaker learning signals or more
        attempts, and topics whose content overlaps the candidate's skills,
        focus areas, strengths/weaknesses, and notes.

        ``keywords`` may be passed in to reuse the same signal weights computed
        once per plan; when omitted they are derived from the analysis.
        """
        if keywords is None:
            keywords = self._candidate_keywords(analysis)

        def score(topic: Topic) -> float:
            return self._topic_score(topic, keywords)

        ranked = sorted(topics, key=score, reverse=True)
        logger.debug(
            "Topic ranking for candidate %s: %s",
            analysis.candidate_id,
            " > ".join(f"{topic.id}={score(topic):.1f}" for topic in ranked),
        )
        return ranked

    def _topic_score(self, topic: Topic, keywords: dict[str, float]) -> float:
        """Relevance of a topic to the candidate's keyword weights."""
        tokens = _tokenize(f"{topic.id} {topic.title} {topic.description}")
        return sum(keywords.get(token, 0.0) for token in tokens)

    def _candidate_keywords(self, analysis: CandidateAnalysis) -> dict[str, float]:
        """Build candidate-topic keyword weights from every profile signal.

        Weights are derived only from data the candidate actually provided —
        nothing is invented. Each signal contributes through a single channel so
        the same token is never double counted:

          * skills, weighted by claimed level (beginner gaps weigh most);
          * focus areas (declared interest);
          * preferred languages and the target role (context);
          * completed learning-journey topics (real exposure);
          * attempt counts, when present;
          * areas for further assessment (gaps to probe);
          * derived strengths (topics to probe at depth);
          * free-text notes.

        ``analysis.learning_signals`` is intentionally not re-read here because
        it already encodes focus areas, languages, and notes fragments; using the
        structured fields directly keeps the weights accurate.
        """
        keywords: dict[str, float] = {}

        def add(text: str, weight: float) -> None:
            for token in _tokenize(text):
                if token in _STOPWORDS:
                    continue
                keywords[token] = keywords.get(token, 0.0) + weight

        profile = analysis.profile

        for skill in profile.skills:
            level = skill.level.strip().lower()
            add(skill.name, _SKILL_LEVEL_WEIGHTS.get(level, 1.0))

        for area in profile.focus_areas:
            add(area, 1.5)

        for language in profile.preferred_languages:
            add(language, 1.0)

        add(profile.role, 1.0)

        for title in analysis.completed_topics:
            add(title, 1.0)

        for subject, count in analysis.attempts.items():
            add(subject, 1.0 + 0.5 * max(0, min(count, 5)))

        for area in analysis.areas_for_further_assessment:
            add(area, 1.5)

        for strength in analysis.strengths:
            add(strength, 1.0)

        add(profile.notes, 1.0)

        return keywords

    def _difficulty_bias(self, analysis: CandidateAnalysis) -> str | None:
        """Return the difficulty bias for a custom candidate profile.

        Only profiles with the ``custom-`` id prefix (user-created in the
        frontend) tune the plan's difficulty mix. ``junior`` leans toward easy
        questions, ``senior`` toward hard, and ``mid`` (or any unknown value)
        stays balanced — same mix as every shipped candidate profile.
        """
        if not analysis.candidate_id.startswith(CUSTOM_PROFILE_PREFIX):
            return None
        level = (analysis.profile.experience_level or "").strip().lower()
        return _EXPERIENCE_TO_BIAS.get(level)

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
        self,
        ordered: list[Topic],
        skipped_ids: set[str],
        target_count: int | None = MIN_QUESTIONS,
        keywords: dict[str, float] | None = None,
        *,
        difficulty_bias: str | None = None,
        variety_seed: str | None = None,
    ) -> list[tuple[Topic, QuestionTemplate]]:
        """Select up to ``target_count`` grounded questions.

        Strategy:
          1. coverage pass — one question from every topic (preferring the tier
             closest to ``difficulty_bias`` when one is set, otherwise the
             easiest), so distinct topics are covered before anything is
             repeated. Explicitly skipped topics are excluded from coverage when
             enough non-skipped topics remain, so skipped areas are only
             revisited if they are genuinely required to build the plan;
          2. fill pass — remaining questions in difficulty-tier order. A
             ``difficulty_bias`` reorders the tiers (hard -> medium -> easy for
             a senior bias) so the harder questions land early and make the cut;
             without a bias the classic easy -> medium -> hard order applies;
          3. variety guards (production only) — when the curriculum provides
             medium or hard questions, ensure at least one of each is present,
             swapping a late non-unique-topic question for the missing tier so
             the harder question lands near the end (realistic progression).

        ``variety_seed`` rotates the order questions are considered inside each
        topic (via :meth:`_seeded_questions`), so different candidates draw
        different questions from the bank while every structural guarantee
        (coverage, tiers, difficulty guards, uniqueness) is preserved. A
        ``None`` seed disables rotation and keeps the classic deterministic
        curriculum order.

        ``target_count`` caps the selected size. A ``None`` target (development
        mode) selects every available question and skips the variety guards so
        in-progress curricula can be previewed in full.
        """
        selected: list[tuple[Topic, QuestionTemplate]] = []
        used: set[str] = set()

        non_skipped = [topic for topic in ordered if topic.id not in skipped_ids]
        include_skipped = target_count is None or len(non_skipped) < MIN_TOPICS

        bias_rank = _DIFFICULTY_RANKS.get(difficulty_bias) if difficulty_bias else None

        for topic in ordered:
            if topic.id in skipped_ids and not include_skipped:
                continue
            question = self._easiest_available(
                topic, used, bias_rank=bias_rank, variety_seed=variety_seed
            )
            if question is not None:
                selected.append((topic, question))
                used.add(question.id)

        for tier in self._tier_order(difficulty_bias):
            tier_rank = _DIFFICULTY_RANKS[tier]
            for topic in ordered:
                if topic.id in skipped_ids and not include_skipped:
                    continue
                for question in self._seeded_questions(topic, variety_seed):
                    if question.id in used or self._difficulty_rank(question.difficulty) != tier_rank:
                        continue
                    selected.append((topic, question))
                    used.add(question.id)
                    if target_count is not None and len(selected) >= target_count:
                        break
                if target_count is not None and len(selected) >= target_count:
                    break
            if target_count is not None and len(selected) >= target_count:
                break

        if target_count is None:
            return selected

        self._ensure_tier("medium", selected, ordered, used, variety_seed=variety_seed)
        self._ensure_tier("hard", selected, ordered, used, variety_seed=variety_seed)

        return selected[:target_count]

    @staticmethod
    def _seeded_questions(
        topic: Topic, variety_seed: str | None
    ) -> list[QuestionTemplate]:
        """The topic's questions in seeded rotation order (stable per seed).

        With a ``variety_seed`` the order is a deterministic function of the
        seed plus each question id, so different candidates meet the topic's
        questions in a different (but reproducible) order. With ``None`` the
        curriculum order is preserved.
        """
        if not variety_seed:
            return list(topic.questions)
        return sorted(
            topic.questions,
            key=lambda question: _stable_hash(variety_seed, topic.id, question.id),
        )

    @staticmethod
    def _tier_order(difficulty_bias: str | None) -> tuple[str, ...]:
        """Fill-pass tier order; a hard bias pulls hard questions forward."""
        if difficulty_bias == "hard":
            return ("hard", "medium", "easy")
        return _DIFFICULTY_ORDER

    def _easiest_available(
        self,
        topic: Topic,
        used: set[str],
        *,
        bias_rank: int | None = None,
        variety_seed: str | None = None,
    ) -> QuestionTemplate | None:
        """Return the topic's best unused question.

        With no ``bias_rank`` this is the easiest unused question (easy <
        medium < hard). With a bias it picks the unused question whose tier is
        closest to the bias (ties go to the easier tier), so a senior-leaning
        plan leads a topic with its hardest question. Within a difficulty tier a
        ``variety_seed`` rotates which question wins, so different candidates
        lead topics with different (but reproducible) questions.
        """
        best: QuestionTemplate | None = None
        best_key = None
        for question in topic.questions:
            if question.id in used:
                continue
            rank = self._difficulty_rank(question.difficulty)
            rotation = (
                _stable_hash(variety_seed, topic.id, question.id)
                if variety_seed
                else 0
            )
            if bias_rank is None:
                key = (rank, rotation)
            else:
                key = (abs(rank - bias_rank), rank, rotation)
            if best_key is None or key < best_key:
                best, best_key = question, key
        return best

    def _ensure_tier(
        self,
        tier: str,
        selected: list[tuple[Topic, QuestionTemplate]],
        ordered: list[Topic],
        used: set[str],
        *,
        variety_seed: str | None = None,
    ) -> None:
        """Guarantee at least one question of ``tier`` when the data allows it."""
        rank = _DIFFICULTY_RANKS[tier]
        if any(self._difficulty_rank(question.difficulty) == rank for _, question in selected):
            return

        replacement: tuple[Topic, QuestionTemplate] | None = None
        for topic in ordered:
            for question in self._seeded_questions(topic, variety_seed):
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
