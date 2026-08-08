/** Conversation labeling helpers.

These derive display-only metadata (progress, current topic, follow-up badges)
from the authoritative conversation already stored in the session. The backend
reply is never modified or guessed at — we only match it against the real
question set shipped in the curriculum data.
*/

import { matchQuestion, parseQuestionCount } from "../data/curriculum";
import type { ChatMessage } from "../types/interview";
import type { AssistantKind } from "../components/ui/ChatBubble";

/** Fallback total when the intro reply cannot be parsed. */
export const DEFAULT_QUESTION_COUNT = 8;

/**
 * Classify one assistant message for display purposes only.
 *
 * Primary questions are matched against the real curriculum question set
 * (identity match — not keyword sniffing). Anything else that is not the
 * opening message is an adaptive follow-up from the backend.
 */
export function classifyAssistantMessage(
  messages: ChatMessage[],
  index: number,
  completed: boolean
): AssistantKind {
  const message = messages[index];
  if (message.role !== "assistant") return "question";
  if (matchQuestion(message.content)) return "question";
  if (index === 0) return "intro";
  if (completed && index === messages.length - 1) return "closing";
  return "follow_up";
}

export interface InterviewProgress {
  asked: number;
  current: number;
  totalQuestions: number;
  topicTitle: string | null;
  fraction: number;
}

export function computeProgress(
  messages: ChatMessage[],
  fallbackTotal = DEFAULT_QUESTION_COUNT
): InterviewProgress {
  let totalQuestions = fallbackTotal;
  const seen = new Map<string, { topicTitle: string; questionId: string }>();

  for (const message of messages) {
    if (message.role !== "assistant") continue;
    if (totalQuestions === fallbackTotal) {
      const parsed = parseQuestionCount(message.content);
      if (parsed !== null) totalQuestions = parsed;
    }
    const match = matchQuestion(message.content);
    if (match && !seen.has(match.questionId)) {
      seen.set(match.questionId, {
        topicTitle: match.topicTitle,
        questionId: match.questionId,
      });
    }
  }

  const asked = seen.size;
  const current = Math.min(asked, totalQuestions);
  const entries = [...seen.values()];
  const last = entries.length > 0 ? entries[entries.length - 1] : null;

  return {
    asked,
    current,
    totalQuestions,
    topicTitle: last?.topicTitle ?? null,
    fraction: totalQuestions > 0 ? current / totalQuestions : 0,
  };
}
