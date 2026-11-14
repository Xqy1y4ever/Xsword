import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api.js";

export function useSession() {
  const [state, setState] = useState({ ready: false, authenticated: false });

  const refresh = useCallback(async () => {
    try {
      const data = await api.me();
      setState({ ready: true, authenticated: Boolean(data.authenticated) });
    } catch {
      setState({ ready: true, authenticated: false });
    }
  }, []);

  useEffect(() => {
    refresh();
    const onExpired = () => setState({ ready: true, authenticated: false });
    window.addEventListener("session-expired", onExpired);
    return () => window.removeEventListener("session-expired", onExpired);
  }, [refresh]);

  const login = useCallback(
    async (password) => {
      await api.login(password);
      await refresh();
    },
    [refresh]
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setState({ ready: true, authenticated: false });
    }
  }, []);

  return { ...state, login, logout, refresh };
}
