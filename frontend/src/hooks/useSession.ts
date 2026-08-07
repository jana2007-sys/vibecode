/** Session data hook.

Loads a single session or the session list from the backend with loading and
error state. Used by the Report page and future session history views.
*/

import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { Session, SessionList } from "../types/session";

interface UseSessionResult {
  loading: boolean;
  error: string | null;
  session: Session | null;
  list: SessionList | null;
  fetchSession: (id: string) => Promise<void>;
  fetchList: () => Promise<void>;
}

export function useSession(): UseSessionResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [list, setList] = useState<SessionList | null>(null);

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

  const fetchSession = useCallback(
    async (id: string) => {
      const result = await run(() => api.getSession(id));
      setSession(result);
    },
    [run]
  );

  const fetchList = useCallback(async () => {
    const result = await run(() => api.listSessions());
    setList(result);
  }, [run]);

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  return { loading, error, session, list, fetchSession, fetchList };
}
