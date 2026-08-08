/** Frontend interview session state.

This is the client-side shape that is persisted to sessionStorage so a page
refresh does not destroy an in-progress interview. It deliberately mirrors only
what the frontend needs — nothing else is stored.
*/

import type { CandidateProfile } from "./candidate";
import type { InterviewFeedback } from "./feedback";
import type { ChatMessage } from "./interview";

export interface InterviewSession {
  sessionId: string | null;
  candidate: CandidateProfile | null;
  messages: ChatMessage[];
  feedback: InterviewFeedback | null;
  done: boolean;
}

export const EMPTY_SESSION: InterviewSession = {
  sessionId: null,
  candidate: null,
  messages: [],
  feedback: null,
  done: false,
};
