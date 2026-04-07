"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchCurrentUser, login, logout, type AuthUser } from "@/src/lib/api/auth";

export function useAuthStatus() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchCurrentUser();
      setUser(response.user);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loginWithPassword = useCallback(async (username: string, password: string) => {
    const response = await login({ username, password });
    setUser(response.user);
    return response.user;
  }, []);

  const logoutCurrentUser = useCallback(async () => {
    await logout();
    setUser(null);
  }, []);

  return {
    user,
    loading,
    isAuthenticated: Boolean(user),
    refresh,
    loginWithPassword,
    logoutCurrentUser,
  };
}
