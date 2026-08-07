/** Interview orchestration hook.

Exposes the start / answer / complete actions backed by the API client, plus
loading and error state. UI pages consume this hook; no fetch calls here.
*/

import { useCallback, useState } from "react";
import { api } from "../services/api";
import type {
  AnswerResponse,
  CompleteInterviewResponse,
  StartInterviewResponse,
} from "../types/interview";

interface UseInterviewResult {
  loading: boolean;
  error: string | null;
  start: (candidateId: string, curriculumId: string) => Promise<StartInterviewResponse>;
  answer: (sessionId: string, content: string) => Promise<AnswerResponse>;
  complete: (sessionId: string) => Promise<CompleteInterviewResponse>;
}

export function useInterview(): UseInterviewResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    setLoading(true);
    setError(null);
    try {
      return await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const start = useCallback(
    (candidateId: string, curriculumId: string) =>
      run(() => api.startInterview({ candidate_id: candidateId, curriculum_id: curriculumId })),
    [run]
  );

  const answer = useCallback(
    (sessionId: string, content: string) =>
      run(() => api.answerInterview(sessionId, { content })),
    [run]
  );

  const complete = useCallback(
    (sessionId: string) => run(() => api.completeInterview(sessionId)),
    [run]
  );

  return { loading, error, start, answer, complete };
}
