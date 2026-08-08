/** Interview API contract types (frontend, camelCase).

The backend contract is a single interactive endpoint:

  POST /interview

  START:
    { sessionId, candidate }
  CONTINUE:
    { sessionId, message }
  RESPONSE (both cases):
    { reply, done, feedback? }

`feedback` is only present when `done` is true. See `InterviewFeedback` in
`./feedback`. The frontend never locally generates questions — the backend reply
is authoritative.
*/

import type { CandidateProfile } from "./candidate";
import type { InterviewFeedback } from "./feedback";

export type ChatRole = "assistant" | "candidate";

/** A single rendered conversation message (client-side). */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
}

/** Body of the first POST /interview call — starts the interview. */
export interface InterviewStartRequest {
  sessionId: string;
  candidate: CandidateProfile;
}

/** Body of subsequent POST /interview calls — submits an answer. */
export interface InterviewContinueRequest {
  sessionId: string;
  message: string;
}

export type InterviewRequest = InterviewStartRequest | InterviewContinueRequest;

/** Response to every POST /interview call. */
export interface InterviewResponse {
  reply: string;
  done: boolean;
  feedback: InterviewFeedback | null;
}
