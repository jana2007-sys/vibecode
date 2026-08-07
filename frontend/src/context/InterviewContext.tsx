/** Global interview state provider.

Holds the active session + candidate selection at the app level so pages can
share state (CandidateSelection -> Interview -> Report) without prop drilling.
*/

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session } from "../types/session";

interface InterviewContextValue {
  session: Session | null;
  candidateId: string | null;
  setSession: (session: Session | null) => void;
  setCandidateId: (id: string | null) => void;
  reset: () => void;
}

const InterviewContext = createContext<InterviewContextValue | undefined>(
  undefined
);

export function InterviewProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [candidateId, setCandidateId] = useState<string | null>(null);

  const value = useMemo<InterviewContextValue>(
    () => ({
      session,
      candidateId,
      setSession,
      setCandidateId,
      reset: () => {
        setSession(null);
        setCandidateId(null);
      },
    }),
    [session, candidateId]
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
