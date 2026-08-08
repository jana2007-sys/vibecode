/** Global interview state provider.

Holds the active session at the app level so pages can share state
(CandidateSelection -> Interview -> Report) without prop drilling. The state is
persisted to sessionStorage so a page refresh does not destroy an in-progress
interview. Only non-sensitive session data is persisted; loading and error
states are deliberately ephemeral.

The backend is the authority: we render whatever `POST /interview` returns and
never generate questions locally.
*/

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, parseInterviewResponse } from "../services/api";
import { describeError } from "../services/http";
import type { CandidateProfile } from "../types/candidate";
import type { ChatMessage } from "../types/interview";
import type { InterviewFeedback } from "../types/feedback";
import { EMPTY_SESSION, type InterviewSession } from "../types/session";

const STORAGE_KEY = "intervue.session.v1";

interface InterviewContextValue extends InterviewSession {
  /** True while a start/continue request is in flight. */
  loading: boolean;
  /** User-friendly message from the last failed request, or null. */
  error: string | null;
  /** Select a candidate (persists across refreshes before the interview starts). */
  setCandidate: (candidate: CandidateProfile) => void;
  /** Start a fresh interview for the given candidate. */
  startInterview: (candidate: CandidateProfile) => Promise<void>;
  /** Submit an answer. Resolves true when the turn was accepted. */
  submitAnswer: (message: string) => Promise<boolean>;
  /** Clear the session and selection. */
  reset: () => void;
}

const InterviewContext = createContext<InterviewContextValue | undefined>(
  undefined
);

function createId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

function makeMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return { id: createId(), role, content, createdAt: new Date().toISOString() };
}

function hydrate(): InterviewSession {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY_SESSION;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return {
      sessionId: typeof parsed.sessionId === "string" ? parsed.sessionId : null,
      candidate: (parsed.candidate as CandidateProfile | null) ?? null,
      messages: Array.isArray(parsed.messages)
        ? (parsed.messages as ChatMessage[])
        : [],
      feedback: (parsed.feedback as InterviewFeedback | null) ?? null,
      done: Boolean(parsed.done),
    };
  } catch {
    return EMPTY_SESSION;
  }
}

export function InterviewProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<InterviewSession>(hydrate);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const sessionRef = useRef(session);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  // Persist the session (selection + conversation) on every change.
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } catch {
      // Storage unavailable (private mode) — the session just won't survive
      // a refresh; the UI still works.
    }
  }, [session]);

  const startInterview = useCallback(async (candidate: CandidateProfile) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setLoading(true);
    setError(null);

    const sessionId = createId();
    try {
      const raw = await api.startInterview(sessionId, candidate);
      const response = parseInterviewResponse(raw);
      setSession({
        sessionId,
        candidate,
        messages: [makeMessage("assistant", response.reply)],
        feedback: response.feedback,
        done: response.done,
      });
    } catch (err) {
      setSession((prev) => ({
        ...prev,
        sessionId: null,
        messages: [],
        feedback: null,
        done: false,
        candidate: candidate ?? prev.candidate,
      }));
      setError(describeError(err));
    } finally {
      setLoading(false);
      busyRef.current = false;
    }
  }, []);

  const submitAnswer = useCallback(async (message: string): Promise<boolean> => {
    const current = sessionRef.current;
    if (busyRef.current || !current.sessionId || message.trim().length === 0) {
      return false;
    }
    busyRef.current = true;
    setLoading(true);
    setError(null);

    try {
      const raw = await api.continueInterview(current.sessionId, message);
      const response = parseInterviewResponse(raw);
      const candidateMsg = makeMessage("candidate", message);
      const assistantMsg = makeMessage("assistant", response.reply);
      setSession((prev) => ({
        ...prev,
        messages: [...prev.messages, candidateMsg, assistantMsg],
        feedback: response.done ? response.feedback : prev.feedback,
        done: response.done,
      }));
      return true;
    } catch (err) {
      setError(describeError(err));
      return false;
    } finally {
      setLoading(false);
      busyRef.current = false;
    }
  }, []);

  const setCandidate = useCallback((candidate: CandidateProfile) => {
    setSession((prev) => ({ ...prev, candidate }));
  }, []);

  const reset = useCallback(() => {
    busyRef.current = false;
    sessionRef.current = EMPTY_SESSION;
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // Storage unavailable — in-memory state is reset regardless.
    }
    setSession(EMPTY_SESSION);
    setError(null);
    setLoading(false);
  }, []);

  const value = useMemo<InterviewContextValue>(
    () => ({
      ...session,
      loading,
      error,
      setCandidate,
      startInterview,
      submitAnswer,
      reset,
    }),
    [session, loading, error, setCandidate, startInterview, submitAnswer, reset]
  );

  return (
    <InterviewContext.Provider value={value}>
      {children}
    </InterviewContext.Provider>
  );
}

export function useInterviewContext(): InterviewContextValue {
  const context = useContext(InterviewContext);
  if (!context) {
    throw new Error("useInterviewContext must be used within InterviewProvider");
  }
  return context;
}
