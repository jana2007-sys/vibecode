/** Structured feedback returned by the backend when an interview completes.

This mirrors the `InterviewFeedback` model in the hackathon contract exactly:
`{ summary, strengths, gaps, next }`. No scores are invented — if the API does
not provide a number, the UI simply never shows one.
*/

export interface InterviewFeedback {
  summary: string;
  strengths: string[];
  gaps: string[];
  next: string[];
}
