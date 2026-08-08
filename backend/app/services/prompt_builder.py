"""Prompt construction.

Assembles prompt payloads for LLM calls: loads static instruction templates
from ``app/prompts/templates`` and appends validated dynamic context (session,
curriculum, candidate answer, deterministic evaluation, conversation).
"""

from __future__ import annotations

from pathlib import Path

from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Structured JSON contract for an adaptive follow-up decision.
FOLLOW_UP_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "should_follow_up": {"type": "BOOLEAN"},
        "reason": {"type": "STRING"},
        "question": {"type": "STRING"},
        "target_concept": {"type": "STRING"},
    },
    "required": ["should_follow_up", "reason", "question", "target_concept"],
}

#: Structured JSON contract for the per-turn adaptive interview decision.
DECISION_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "action": {"type": "STRING"},
        "reason": {"type": "STRING"},
        "question": {"type": "STRING"},
        "target_concept": {"type": "STRING"},
    },
    "required": ["action", "reason", "question", "target_concept"],
}

#: Structured JSON contract for the AI-generated final feedback report.
FEEDBACK_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "overall_summary": {"type": "STRING"},
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "improvement_areas": {"type": "ARRAY", "items": {"type": "STRING"}},
        "next_steps": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["overall_summary", "strengths", "improvement_areas", "next_steps"],
}

#: How many recent transcript turns to include for context, and per-turn cap.
MAX_CONTEXT_TURNS = 10
MAX_TURN_CHARS = 500


class PromptBuilder:
    """Builds prompt payloads for LLM calls."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        #: Default to backend/app/prompts/templates unless overridden.
        self._templates_dir = templates_dir or (
            Path(__file__).resolve().parent.parent / "prompts" / "templates"
        )

    def load_template(self, template_name: str) -> str:
        """Read a named template file from the templates directory."""
        name = template_name if template_name.endswith(".txt") else f"{template_name}.txt"
        path = self._templates_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        return path.read_text(encoding="utf-8")

    def build_follow_up_prompt(
        self,
        *,
        session_id: str,
        topic: dict,
        question: dict,
        answer: str,
        evaluation: dict,
        conversation_context: list[dict],
    ) -> str:
        """Compose the prompt for an adaptive follow-up decision.

        Grounds the decision in the curriculum topic, the current question and
        its expected concepts, the candidate's actual answer, the deterministic
        evaluation, and the recent conversation.
        """
        template = self.load_template("follow_up")
        context_block = self._format_follow_up_context(
            session_id,
            topic,
            question,
            answer,
            evaluation,
            conversation_context,
        )
        return template.strip() + "\n\n" + context_block

    def build_decision_prompt(
        self,
        *,
        session_id: str,
        topic: dict,
        question: dict,
        answer: str,
        evaluation: dict,
        conversation_context: list[dict],
        remaining_questions: int,
        difficulty_bias: str | None,
    ) -> str:
        """Compose the prompt for the per-turn adaptive interview decision.

        Grounds the decision in the curriculum topic, the current question and
        its expected concepts, the candidate's actual answer, the deterministic
        evaluation, the recent conversation, how many primary questions remain,
        and the plan's difficulty bias.
        """
        template = self.load_template("decision")
        context_block = self._format_decision_context(
            session_id,
            topic,
            question,
            answer,
            evaluation,
            conversation_context,
            remaining_questions,
            difficulty_bias,
        )
        return template.strip() + "\n\n" + context_block

    def build_question_prompt(self, session_id: str, question: str) -> str:
        """Compose the prompt for generating the next interviewer question.

        Placeholder: no prompt construction yet.
        """
        raise NotImplementedError("Prompt building will be implemented later.")

    def build_evaluation_prompt(self, session_id: str, answer: str) -> str:
        """Compose the prompt for scoring a candidate answer.

        Placeholder: no prompt construction yet.
        """
        raise NotImplementedError("Prompt building will be implemented later.")

    def build_feedback_prompt(self, session_id: str, *, context: dict) -> str:
        """Compose the prompt for generating the final report narrative.

        Grounds the report in the candidate profile, the per-topic performance,
        the overall score, and the question-by-question evaluations with their
        matched (covered) and missing concepts.
        """
        template = self.load_template("feedback")
        context_block = self._format_feedback_context(session_id, context)
        return template.strip() + "\n\n" + context_block

    @staticmethod
    def _format_follow_up_context(
        session_id: str,
        topic: dict,
        question: dict,
        answer: str,
        evaluation: dict,
        conversation_context: list[dict],
    ) -> str:
        """Render the dynamic context block appended to the follow-up template."""
        topic = topic or {}
        question = question or {}
        evaluation = evaluation or {}
        expected = ", ".join(question.get("expects", []) or [])
        missing = ", ".join(evaluation.get("missing", []) or [])
        covered = ", ".join(evaluation.get("covered", []) or [])

        lines = [
            "=== CONTEXT ===",
            f"session_id: {session_id}",
            "",
            "CURRICULUM TOPIC",
            f"  id: {topic.get('id', '')}",
            f"  title: {topic.get('title', '')}",
            f"  description: {topic.get('description', '')}",
            "",
            "CURRENT QUESTION",
            f"  id: {question.get('curriculum_question_id', '')}",
            f"  text: {question.get('text', '')}",
            f"  difficulty: {question.get('difficulty', '')}",
            f"  expected concepts: {expected}",
            "",
            "CANDIDATE'S ANSWER",
            f"  {answer or ''}",
            "",
            "DETERMINISTIC EVALUATION",
            f"  score: {evaluation.get('score', '')}/10",
            f"  covered concepts: {covered or '(none)'}",
            f"  missing concepts: {missing or '(none)'}",
            "",
            "CONVERSATION CONTEXT (recent turns)",
        ]
        turns = (conversation_context or [])[-MAX_CONTEXT_TURNS:]
        if not turns:
            lines.append("  (no prior turns)")
        for turn in turns:
            role = str(turn.get("role", "unknown"))
            content = str(turn.get("content", ""))[:MAX_TURN_CHARS]
            lines.append(f"  {role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_decision_context(
        session_id: str,
        topic: dict,
        question: dict,
        answer: str,
        evaluation: dict,
        conversation_context: list[dict],
        remaining_questions: int,
        difficulty_bias: str | None,
    ) -> str:
        """Render the dynamic context block appended to the decision template."""
        topic = topic or {}
        question = question or {}
        evaluation = evaluation or {}
        expected = ", ".join(question.get("expects", []) or [])
        missing = ", ".join(evaluation.get("missing", []) or [])
        covered = ", ".join(evaluation.get("covered", []) or [])

        lines = [
            "=== CONTEXT ===",
            f"session_id: {session_id}",
            "",
            "CURRICULUM TOPIC",
            f"  id: {topic.get('id', '')}",
            f"  title: {topic.get('title', '')}",
            f"  description: {topic.get('description', '')}",
            "",
            "CURRENT QUESTION",
            f"  id: {question.get('curriculum_question_id', '')}",
            f"  text: {question.get('text', '')}",
            f"  difficulty: {question.get('difficulty', '')}",
            f"  expected concepts: {expected}",
            "",
            "CANDIDATE'S ANSWER",
            f"  {answer or ''}",
            "",
            "DETERMINISTIC EVALUATION",
            f"  score: {evaluation.get('score', '')}/10",
            f"  covered concepts: {covered or '(none)'}",
            f"  missing concepts: {missing or '(none)'}",
            "",
            "PLAN STATE",
            f"  remaining primary questions: {remaining_questions}",
            f"  difficulty_bias: {difficulty_bias or 'balanced'}",
            "",
            "CONVERSATION CONTEXT (recent turns)",
        ]
        turns = (conversation_context or [])[-MAX_CONTEXT_TURNS:]
        if not turns:
            lines.append("  (no prior turns)")
        for turn in turns:
            role = str(turn.get("role", "unknown"))
            content = str(turn.get("content", ""))[:MAX_TURN_CHARS]
            lines.append(f"  {role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_feedback_context(session_id: str, context: dict) -> str:
        """Render the dynamic context block appended to the feedback template.

        Every statement the model can make must be traceable back to this block:
        the candidate profile, per-topic averages, the overall score, and each
        question with its actual answer, score, covered concepts, and missing
        concepts.
        """
        context = context or {}
        candidate = context.get("candidate") or {}
        profile = candidate.get("profile") or {}
        topic_summaries = context.get("topic_summaries") or []
        evaluations = context.get("evaluations") or []

        skills = ", ".join(
            skill.get("name", "")
            for skill in profile.get("skills", []) or []
            if skill.get("name")
        )
        focus = ", ".join(profile.get("focus_areas", []) or [])
        derived = ", ".join(candidate.get("strengths", []) or [])
        areas = ", ".join(candidate.get("areas_for_further_assessment", []) or [])

        lines = [
            "=== CONTEXT ===",
            f"session_id: {session_id}",
            "",
            "CANDIDATE PROFILE",
            f"  name: {profile.get('name', '')}",
            f"  target role: {profile.get('role', '')}",
            f"  years of experience: {profile.get('years_of_experience', '')}",
            f"  skills: {skills or '(none)'}",
            f"  focus areas: {focus or '(none)'}",
            f"  derived strengths: {derived or '(none)'}",
            f"  areas for further assessment: {areas or '(none)'}",
            "",
            "TOPIC PERFORMANCE",
        ]
        if not topic_summaries:
            lines.append("  (no topics scored)")
        for topic in topic_summaries:
            lines.append(
                f"  {topic.get('title', topic.get('topic_id', ''))} "
                f"({topic.get('topic_id', '')}): average score "
                f"{topic.get('average_score', 0)}/10"
            )
        lines.append("")
        lines.append(f"OVERALL SCORE: {context.get('overall_score', 0)}/10")
        lines.append("")

        lines.append("QUESTION-BY-QUESTION EVALUATIONS")
        if not evaluations:
            lines.append("  (no evaluations)")
        for index, evaluation in enumerate(evaluations, start=1):
            kind = str(evaluation.get("kind", "primary"))
            question = evaluation.get("question", "")
            answer = str(evaluation.get("answer", ""))[:MAX_TURN_CHARS]
            score = evaluation.get("score", 0)
            covered = ", ".join(evaluation.get("covered", []) or [])
            missing = ", ".join(evaluation.get("missing", []) or [])
            lines.append(f"  {index}. [{kind}] {question}")
            if answer:
                lines.append(f"     candidate answer: {answer}")
            lines.append(f"     score: {score}/10")
            lines.append(f"     covered concepts: {covered or '(none)'}")
            lines.append(f"     missing concepts: {missing or '(none)'}")
        return "\n".join(lines)
