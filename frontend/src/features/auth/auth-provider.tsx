"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, request } from "@/shared/api";
import { applySession, authenticatedRequest, clearSession, recoverSession, type AuthResponse, type User } from "./session";

type AuthState = {
  user: User | null; ready: boolean; error: string;
  login: (email: string, password: string, register: boolean) => Promise<void>;
  logout: () => Promise<void>; invalidate: () => void; retry: () => void;
};
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const invalidate = useCallback(() => { clearSession(); setUser(null); }, []);

  useEffect(() => {
    let cancelled = false;
    setReady(false); setError("");
    recoverSession().then(result => { if (!cancelled) setUser(result.user); }).catch(error => {
      if (!cancelled) {
        setUser(null);
        if (!(error instanceof ApiError) || error.status !== 401) setError(error.message);
      }
    }).finally(() => { if (!cancelled) setReady(true); });
    return () => { cancelled = true; };
  }, [attempt]);

  async function login(email: string, password: string, register: boolean) {
    const result = await request<AuthResponse>(register ? "/auth/register" : "/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    });
    applySession(result); setUser(result.user); setError(""); setReady(true);
  }
  async function logout() {
    await authenticatedRequest("/auth/logout", { method: "POST" });
    invalidate();
  }
  return <AuthContext.Provider value={{ user, ready, error, login, logout, invalidate, retry: () => setAttempt(n => n + 1) }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const state = useContext(AuthContext);
  if (!state) throw new Error("로그인 상태를 확인할 수 없습니다.");
  return state;
}
