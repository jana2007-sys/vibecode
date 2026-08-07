/** Mirrors backend `InterviewState` enum. */
export type InterviewState =
  | "START"
  | "INTRODUCTION"
  | "QUESTION"
  | "FOLLOW_UP"
  | "NEXT_TOPIC"
  | "SUMMARY"
  | "COMPLETED";

/** Mirrors backend `SessionRead`. */
export interface Session {
  id: string;
  candidate_id: string;
  curriculum_id: string;
  state: InterviewState;
  topic_index: number;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

/** Mirrors backend `SessionList`. */
export interface SessionList {
  items: Session[];
  total: number;
}
