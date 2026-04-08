"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchCurrentUser, login, logout, type AuthUser } from "@/src/lib/api/auth";

let sharedUser: AuthUser | null = null;
let sharedLoading = true;
let hasInitialized = false;
let refreshTask: Promise<void> | null = null;
const subscribers = new Set<() => void>();

const notifySubscribers = () => {
  subscribers.forEach((callback) => callback());
};

const setSharedAuthState = (params: { user?: AuthUser | null; loading?: boolean }) => {
  if (params.user !== undefined) {
    sharedUser = params.user;
  }
  if (params.loading !== undefined) {
    sharedLoading = params.loading;
  }
  notifySubscribers();
};

const refreshSharedAuthState = async () => {
  if (refreshTask) {
    return refreshTask;
  }

  refreshTask = (async () => {
    setSharedAuthState({ loading: true });
    try {
      const response = await fetchCurrentUser();
      setSharedAuthState({ user: response.user });
    } catch {
      setSharedAuthState({ user: null });
    } finally {
      setSharedAuthState({ loading: false });
      refreshTask = null;
    }
  })();

  return refreshTask;
};

export function useAuthStatus() {
  const [user, setUser] = useState<AuthUser | null>(sharedUser);
  const [loading, setLoading] = useState(sharedLoading);

  useEffect(() => {
    const syncFromSharedState = () => {
      setUser(sharedUser);
      setLoading(sharedLoading);
    };

    subscribers.add(syncFromSharedState);
    syncFromSharedState();

    if (!hasInitialized) {
      hasInitialized = true;
      void refreshSharedAuthState();
    }

    return () => {
      subscribers.delete(syncFromSharedState);
    };
  }, []);

  const refresh = useCallback(async () => {
    await refreshSharedAuthState();
  }, []);

  const loginWithPassword = useCallback(async (username: string, password: string) => {
    const response = await login({ username, password });
    setSharedAuthState({ user: response.user, loading: false });
    return response.user;
  }, []);

  const logoutCurrentUser = useCallback(async () => {
    await logout();
    setSharedAuthState({ user: null, loading: false });
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
