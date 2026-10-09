"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useAuth } from "@/features/auth/auth-provider";
import { authenticatedRequest } from "@/features/auth/session";
import { ApiError } from "@/shared/api";
import { SelectionGate, type Company } from "./selection-state";

type CompanyState = {
  companies: Company[]; active: Company | null; loading: boolean; error: string;
  select: (id: string) => Promise<void>; reload: () => void;
};
const CompanyContext = createContext<CompanyState | null>(null);

export function CompanyProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [active, setActive] = useState<Company | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const gate = useRef(new SelectionGate());
  const userId = auth.user?.id;
  const invalidate = auth.invalidate;

  const select = useCallback(async (id: string) => {
    const current = gate.current.next();
    setActive(null); setLoading(true); setError("");
    try {
      // 선택한 UUID는 권한이 아닙니다. 서버에서 현재 membership과 permission을 다시 확인합니다.
      const company = await authenticatedRequest<Company>(`/companies/${encodeURIComponent(id)}`);
      if (gate.current.accepts(current)) setActive(company);
    } catch (error) {
      if (gate.current.accepts(current)) {
        setError(error instanceof Error ? error.message : "회사에 접근할 수 없습니다.");
        if (error instanceof ApiError && error.status === 401) invalidate();
      }
    } finally { if (gate.current.accepts(current)) setLoading(false); }
  }, [invalidate]);

  useEffect(() => {
    const current = gate.current.next();
    setCompanies([]); setActive(null); setError("");
    if (!userId) { setLoading(false); return; }
    setLoading(true);
    authenticatedRequest<Company[]>("/companies").then(list => {
      if (!gate.current.accepts(current)) return;
      setCompanies(list); setLoading(false);
      if (list.length === 1) void select(list[0].id);
    }).catch(error => {
      if (!gate.current.accepts(current)) return;
      setLoading(false); setError(error.message);
      if (error instanceof ApiError && error.status === 401) invalidate();
    });
    return () => { gate.current.next(); };
  }, [userId, attempt, select, invalidate]);

  return <CompanyContext.Provider value={{ companies, active, loading, error, select, reload: () => setAttempt(n => n + 1) }}>{children}</CompanyContext.Provider>;
}
export function useCompany() {
  const state = useContext(CompanyContext);
  if (!state) throw new Error("회사 정보를 확인할 수 없습니다.");
  return state;
}
