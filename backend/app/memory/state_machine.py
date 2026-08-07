"""Canonical interview state machine.

Defines the allowed state transitions used by the InterviewEngine. Transitions
are data-driven so new states can be added without changing engine logic.

Canonical flow::

    START -> INTRODUCTION -> QUESTION -> FOLLOW_UP -> NEXT_TOPIC -> SUMMARY -> COMPLETED
                                  ^          |            |
                                  |__________|            |
                                                          v
                                                     (back to QUESTION or SUMMARY)
"""

from __future__ import annotations

from app.models.session import InterviewState
from app.utils.errors import StateTransitionError


class StateMachine:
    """Validates and performs transitions between interview states."""

    #: Allowed transitions: source -> set of legal destination states.
    TRANSITIONS: dict[InterviewState, set[InterviewState]] = {
        InterviewState.START: {InterviewState.INTRODUCTION},
        InterviewState.INTRODUCTION: {InterviewState.QUESTION},
        InterviewState.QUESTION: {
            InterviewState.FOLLOW_UP,
            InterviewState.NEXT_TOPIC,
            InterviewState.SUMMARY,
        },
        InterviewState.FOLLOW_UP: {
            InterviewState.QUESTION,
            InterviewState.NEXT_TOPIC,
            InterviewState.SUMMARY,
        },
        InterviewState.NEXT_TOPIC: {
            InterviewState.QUESTION,
            InterviewState.SUMMARY,
        },
        InterviewState.SUMMARY: {InterviewState.COMPLETED},
        InterviewState.COMPLETED: set(),
    }

    def can_transition(self, current: InterviewState, target: InterviewState) -> bool:
        """Return True when ``current -> target`` is a legal transition."""
        return target in self.TRANSITIONS.get(current, set())

    def transition(self, current: InterviewState, target: InterviewState) -> InterviewState:
        """Perform a validated transition, raising on illegal moves."""
        if not self.can_transition(current, target):
            raise StateTransitionError(
                f"Illegal transition from {current.value} to {target.value}"
            )
        return target
