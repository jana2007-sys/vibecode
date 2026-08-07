/** Typed API client for the InterVue AI backend.

Every method maps 1:1 to a backend route and returns the matching contract type
(see `src/types`). Pages and hooks depend on this client, never on fetch.
*/

import type {
  AnswerRequest,
  AnswerResponse,
  CompleteInterviewResponse,
  StartInterviewRequest,
  StartInterviewResponse,
} from "../types/interview";
import type { Feedback } from "../types/feedback";
import type { Session, SessionList } from "../types/session";
import { http } from "./http";

export const api = {
  health: () => http.get<{ status: string; version: string }>("/health"),

  startInterview: (body: StartInterviewRequest) =>
    http.post<StartInterviewResponse>("/interview", body),

  answerInterview: (sessionId: string, body: AnswerRequest) =>
    http.post<AnswerResponse>(`/interview/${sessionId}/answer`, body),

  completeInterview: (sessionId: string) =>
    http.post<CompleteInterviewResponse>(`/interview/${sessionId}/complete`, {}),

  getSession: (sessionId: string) =>
    http.get<Session>(`/interview/${sessionId}`),

  listSessions: () => http.get<SessionList>("/sessions"),

  getReport: (sessionId: string) =>
    http.get<Feedback>(`/sessions/${sessionId}/report`),
};
