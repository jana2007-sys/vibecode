/** Mirrors backend `TopicSummary`. */
export interface TopicSummary {
  topic_id: string;
  title: string;
  average_score: number;
  strengths: string[];
  improvements: string[];
}

/** Mirrors backend `FeedbackRead`. */
export interface Feedback {
  id: string;
  session_id: string;
  overall_score: number;
  summary: string;
  strengths: string[];
  improvements: string[];
  topics: TopicSummary[];
  created_at: string;
}
