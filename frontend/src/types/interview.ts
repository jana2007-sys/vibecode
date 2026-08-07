/** Mirrors backend request/response contracts for the interview flow. */

export type MessageRole = "system" | "interviewer" | "candidate";

/** Mirrors backend `StartInterviewRequest`. */
export interface StartInterviewRequest {
  candidate_id: string;
  curriculum_id: string;
}

/** Mirrors backend `StartInterviewResponse`. */
export interface StartInterviewResponse {
  session_id: string;
  state: string;
  message: string;
  payload: Record<string, unknown>;
}

/** Mirrors backend `AnswerRequest`. */
export interface AnswerRequest {
  content: string;
}

/** Mirrors backend `AnswerResponse`. */
export interface AnswerResponse {
  session_id: string;
  state: string;
  message: string;
  role: MessageRole;
  payload: Record<string, unknown>;
}

/** Mirrors backend `CompleteInterviewResponse`. */
export interface CompleteInterviewResponse {
  session_id: string;
  state: string;
  report_id: string | null;
  message: string;
  payload: Record<string, unknown>;
}
