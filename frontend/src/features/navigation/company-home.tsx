"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { authenticatedRequest } from "@/features/auth/session";
import type { Company } from "@/features/companies/selection-state";
import type { Workspace } from "@/features/onboarding/model";
import { OnboardingWorkspace } from "@/features/onboarding/onboarding-workspace";
import { AccountingDashboard } from "./accounting-dashboard";

export function CompanyHome({ company }: { company: Company }) {
  const [workspace, setWorkspace] = useState<Workspace>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const canRead = company.permissions.includes("onboarding.read");
  useEffect(() => {
    if (!canRead) return;
    let current = true;
    authenticatedRequest<Workspace>("/onboarding", { headers: { "X-Company-ID": company.id } })
      .then(value => { if (current) { setWorkspace(value); setError(""); } })
      .catch(error => { if (current) setError(error.message); });
    return () => { current = false; };
  }, [company.id, canRead, retry]);
  if (!canRead) return <AccountingDashboard company={company} />;
  if (error) return <section className="panel"><h2>회계 준비 상태를 확인하지 못했습니다</h2><p role="alert">{error}</p><p>입력 권한이 없다면 회사 관리자에게 초기 설정을 요청해 주세요.</p><button onClick={() => setRetry(n => n + 1)}>다시 확인</button> <Link href="/companies">회사 확인</Link></section>;
  if (!workspace) return <p role="status">회계 준비 상태를 확인하고 있습니다…</p>;
  if (workspace.status !== "COMPLETED") return <OnboardingWorkspace company={company} initialWorkspace={workspace} onCompleted={setWorkspace} />;
  return <><div className="setup-finished"><span>회계 준비를 마쳤습니다. 변경할 내용은 설정에서 관리하세요.</span><Link href="/accounting">설정 관리 →</Link></div><AccountingDashboard company={company} /></>;
}
