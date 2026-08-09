/** Typed API client for the InterVue AI backend.

Maps 1:1 to the interactive hackathon contract — a single `POST /interview`
endpoint used for both starting the interview (with a candidate) and continuing
it (with a message). Every response is `{ reply, done, feedback? }`.

The old `answer`/`complete` sub-resource endpoints are intentionally gone; the
frontend depends only on the interactive contract. The base URL comes from
`VITE_API_BASE_URL` (never hardcoded).
*/

import type { Candidate, CandidateCreate, CandidateProfile } from "../types/candidate";
import type { InterviewResponse } from "../types/interview";
import type { InterviewHistory, InterviewReport } from "../types/report";
import { buildUrl, http } from "./http";

/** Coerce an unknown JSON body into the contract shape, or throw. */
export function parseInterviewResponse(value: unknown): InterviewResponse {
  if (!value || typeof value !== "object") {
    throw malformed();
  }
  const raw = value as Record<string, unknown>;
  if (typeof raw.reply !== "string" || raw.reply.length === 0) {
    throw malformed();
  }
  if (typeof raw.done !== "boolean") {
    throw malformed();
  }

  let feedback: InterviewResponse["feedback"] = null;
  if (raw.feedback !== undefined && raw.feedback !== null) {
    if (typeof raw.feedback !== "object") throw malformed();
    const f = raw.feedback as Record<string, unknown>;
    if (
      typeof f.summary !== "string" ||
      !Array.isArray(f.strengths) ||
      !Array.isArray(f.gaps) ||
      !Array.isArray(f.next)
    ) {
      throw malformed();
    }
    feedback = {
      summary: f.summary,
      strengths: f.strengths.map(String),
      gaps: f.gaps.map(String),
      next: f.next.map(String),
    };
  }

  return { reply: raw.reply, done: raw.done, feedback };
}

function malformed(): Error {
  const error = new Error(
    "The interview service returned an unexpected response."
  );
  error.name = "UnexpectedResponseError";
  return error;
}

export const api = {
  health: () => http.get<{ status: string; version: string }>("/health"),

  startInterview: (sessionId: string, candidate: CandidateProfile) =>
    http.post<unknown>("/interview", { sessionId, candidate }),

  continueInterview: (sessionId: string, message: string) =>
    http.post<unknown>("/interview", { sessionId, message }),

  listCandidates: () => http.get<{ items: Candidate[]; total: number }>("/candidates"),

  createCandidate: (body: CandidateCreate) =>
    http.post<Candidate>("/candidates", body),

  getCandidateHistory: (candidateId: string) =>
    http.get<InterviewHistory>(`/candidates/${candidateId}/interviews`),

  clearHistory: (candidateId: string) =>
    http.del<{ deleted: boolean; deleted_sessions: number }>(
      `/candidates/${candidateId}/interviews`
    ),

  deleteCandidate: (candidateId: string) =>
    http.del<{ deleted: boolean; deleted_sessions: number }>(
      `/candidates/${candidateId}`
    ),

  getReport: (candidateId: string, sessionId: string) =>
    http.get<InterviewReport>(`/candidates/${candidateId}/interviews/${sessionId}/report`),

  reportPdfUrl: (candidateId: string, sessionId: string) =>
    buildUrl(`/candidates/${candidateId}/interviews/${sessionId}/report/pdf`),
};
