/** Report and history contracts from the backend.

A "report" is the full persisted artifact for one completed interview: the
candidate summary, the structured feedback, and the transcript. History is the
per-candidate list of interviews with their overall scores.
*/

export interface ReportMessage {
  id: string;
  role: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface ReportCandidate {
  id: string;
  name: string;
  role: string;
  email?: string | null;
  strengths?: string[];
}

export interface ReportTopic {
  topic_id: string;
  title: string;
  average_score: number;
  strengths?: string[];
  improvements?: string[];
}

export interface AnswerReview {
  question_id: string;
  topic_id: string;
  topic_title: string;
  question: string;
  answer: string;
  score: number;
  rationale: string;
  verdict: string;
}

export interface ReportFeedback {
  id: string;
  session_id: string;
  overall_score: number;
  summary: string;
  strengths: string[];
  improvements: string[];
  topics: ReportTopic[];
  created_at: string;
  source: string;
}

export interface InterviewReport {
  session_id: string;
  candidate: ReportCandidate;
  feedback: ReportFeedback;
  completed_at?: string | null;
  messages?: ReportMessage[];
  answer_reviews?: AnswerReview[];
}

export interface InterviewHistoryItem {
  session_id: string;
  state: string;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  overall_score?: number | null;
  summary: string;
}

export interface InterviewHistory {
  candidate_id: string;
  items: InterviewHistoryItem[];
  total: number;
}
