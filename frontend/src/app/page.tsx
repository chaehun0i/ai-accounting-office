"use client";

import { TransactionWorkspace } from "@/features/transactions/transaction-workspace";
import { JournalWorkspace } from "@/features/accounting/journal-workspace";
import { AccountingMaster } from "@/features/accounting/accounting-master";
import { OnboardingWorkspace } from "@/features/onboarding/onboarding-workspace";
import { DataImport } from "@/features/imports/data-import";
import { useState } from "react";
import { AuthProvider, useAuth } from "@/features/auth/auth-provider";
import { AuthForm } from "@/features/auth/auth-form";
import { CompanyProvider, useCompany } from "@/features/companies/company-provider";
import { CompanySelector } from "@/features/companies/components/company-selector";
import { CompanyCreate } from "@/features/companies/components/company-create";

function Office() {
  const auth = useAuth();
  const company = useCompany();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function logout() {
    setBusy(true); setError("");
    try { await auth.logout(); }
    catch (error) { setError(error instanceof Error ? error.message : "로그아웃하지 못했습니다."); }
    finally { setBusy(false); }
  }
  if (!auth.ready) return <p className="panel" role="status">로그인 상태를 확인하고 있습니다…</p>;
  if (!auth.user) return <AuthForm />;
  return <>
    <div className="session-bar"><span>{auth.user.email}</span><button onClick={logout} disabled={busy}>{busy ? "처리 중…" : "로그아웃"}</button></div>
    {error && <p role="alert" className="error">{error}</p>}
    {company.error && <div className="panel" role="alert"><p>{company.error}</p><button onClick={company.reload}>회사 목록 다시 확인</button></div>}
    {company.loading && <p role="status">회사 정보를 확인하고 있습니다…</p>}
    {!company.loading && !company.error && company.companies.length === 0 && <section className="panel"><h2>아직 연결된 회사가 없습니다</h2><p>새 회사를 만들거나 회사 관리자에게 초대를 요청해 주세요.</p></section>}
    {company.companies.length > 0 && <CompanySelector />}
    {company.active && <section className="panel active-company" key={`profile:${company.active.id}`} aria-live="polite">
      <p className="eyebrow">현재 선택한 회사</p><h2>{company.active.company_name}</h2>
      <p>{company.active.permissions.includes("company.update") ? "회사 정보를 관리할 수 있는 권한으로 접속했습니다." : "현재 회사 정보를 조회할 수 있습니다. 정보 수정은 회사 관리자에게 요청해 주세요."}</p>
      <p className="muted">선택한 회사의 회계 기준 정보를 확인할 수 있습니다.</p>
    </section>}
    {company.active && <OnboardingWorkspace key={`onboarding:${company.active.id}`} company={company.active} />}
    {company.active && <TransactionWorkspace key={`transactions:${company.active.id}`} company={company.active} />}
    {company.active && <JournalWorkspace key={`journals:${company.active.id}`} company={company.active} />}
    {company.active && <AccountingMaster key={`accounting:${company.active.id}`} company={company.active} />}
    {company.active && <DataImport key={`imports:${company.active.id}`} company={company.active} />}
    <CompanyCreate />
  </>;
}
export default function Home() {
  return <AuthProvider><CompanyProvider><main><header><p className="eyebrow">회계와 세무를 함께, 명확하게</p><h1>AI Accounting Office</h1></header><Office /></main></CompanyProvider></AuthProvider>;
}
